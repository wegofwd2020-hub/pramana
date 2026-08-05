"""Audit + evidence HTTP router (auditor-facing, RBAC-gated).

Every route here requires the ``Auditor`` or ``ComplianceAdmin`` role. Reads are
tenant-scoped; chain verification runs over the whole (global) chain. Producing
an export is itself recorded to the audit log (US-FCPA-0006 AC3) — extracting
evidence is an auditable event.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api.dependencies import get_db_session, require_roles
from pramana.api.schemas import (
    AssignmentEvidenceOut,
    AuditLogOut,
    AuditLogPage,
    CertificateOut,
    ChainBreakOut,
    ChainVerificationOut,
    EvidenceAttemptOut,
    EvidenceBinderOut,
    Pagination,
)
from pramana.db.models.identity import RoleName
from pramana.domain.assignment_state import utcnow
from pramana.services import audit_query, evidence
from pramana.services.audit import append_audit
from pramana.services.auth import Principal

_AUDITOR = require_roles(RoleName.AUDITOR, RoleName.COMPLIANCE_ADMIN)

router = APIRouter(prefix="/audit", tags=["audit"])
evidence_router = APIRouter(prefix="/evidence", tags=["audit"])

Session = Annotated[AsyncSession, Depends(get_db_session)]
Auditor = Annotated[Principal, Depends(_AUDITOR)]


@router.get("/verify", response_model=ChainVerificationOut)
async def verify_chain(session: Session, _auditor: Auditor) -> ChainVerificationOut:
    """Recompute and verify the entire audit hash chain."""
    result = await audit_query.verify_stored_chain(session)
    return ChainVerificationOut(
        ok=result.ok,
        total=result.total,
        first_break=(
            ChainBreakOut(
                audit_id=result.first_break.audit_id,
                reason=result.first_break.reason,
                expected=result.first_break.expected,
                found=result.first_break.found,
            )
            if result.first_break is not None
            else None
        ),
    )


@router.get("", response_model=AuditLogPage)
async def search_audit(
    session: Session,
    auditor: Auditor,
    actor_user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    event_type: str | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditLogPage:
    """Search the tenant's audit log."""
    rows, total = await audit_query.search_audit(
        session,
        tenant_id=auditor.tenant_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
        page=page,
        page_size=page_size,
    )
    return AuditLogPage(
        items=[AuditLogOut.of(r) for r in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get("/export", response_model=None)
async def export_audit(
    session: Session,
    auditor: Auditor,
    format: Annotated[str, Query(pattern="^(json|csv)$")] = "json",
    actor_user_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    event_type: str | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
) -> Response:
    """Export matching audit rows (JSON or CSV), hashes included for re-verification.

    Producing the export is itself recorded as an ``audit.exported`` event.
    """
    rows = await audit_query.export_audit(
        session,
        tenant_id=auditor.tenant_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
    )

    await append_audit(
        session,
        tenant_id=auditor.tenant_id,
        actor_user_id=auditor.user_id,
        entity_type="audit_log",
        entity_id="export",
        event_type="audit.exported",
        payload={"format": format, "row_count": len(rows), "entity_type": entity_type},
        occurred_at=utcnow(),
    )

    if format == "csv":
        return Response(content=_to_csv(rows), media_type="text/csv")
    payload = [AuditLogOut.of(r).model_dump(mode="json") for r in rows]
    return Response(content=json.dumps(payload), media_type="application/json")


@evidence_router.get("/{user_id}", response_model=EvidenceBinderOut)
async def get_evidence_binder(
    user_id: uuid.UUID,
    session: Session,
    auditor: Auditor,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
) -> EvidenceBinderOut:
    """The full training-evidence binder for one user."""
    binder = await evidence.build_evidence_binder(
        session,
        tenant_id=auditor.tenant_id,
        user_id=user_id,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
    )
    return EvidenceBinderOut(
        user_id=binder.user_id,
        user_email=binder.user_email,
        items=[
            AssignmentEvidenceOut(
                assignment_id=item.assignment.id,
                course_id=item.assignment.course_id,
                course_title=item.course_title,
                course_version_id=item.assignment.course_version_id,
                course_version_number=item.course_version_number,
                status=item.assignment.status,
                assigned_at=getattr(item.assignment, "assigned_at", None),
                terminal_at=item.assignment.terminal_at,
                attempts=[
                    EvidenceAttemptOut(
                        attempt_number=at.attempt_number,
                        outcome=at.outcome,
                        score_pct=at.score_pct,
                        submitted_at=at.submitted_at,
                    )
                    for at in item.attempts
                ],
                certificate=(
                    CertificateOut.of(item.certificate) if item.certificate is not None else None
                ),
            )
            for item in binder.items
        ],
    )


def _to_csv(rows: object) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "audit_id",
            "occurred_at",
            "tenant_id",
            "actor_user_id",
            "entity_type",
            "entity_id",
            "event_type",
            "payload",
            "prev_audit_hash",
            "audit_hash",
        ]
    )
    for r in rows:  # type: ignore[attr-defined]
        writer.writerow(
            [
                r.audit_id,
                r.occurred_at.isoformat(),
                str(r.tenant_id),
                str(r.actor_user_id) if r.actor_user_id else "",
                r.entity_type,
                r.entity_id,
                r.event_type,
                json.dumps(r.payload, sort_keys=True, separators=(",", ":")),
                r.prev_audit_hash or "",
                r.audit_hash,
            ]
        )
    return buf.getvalue()
