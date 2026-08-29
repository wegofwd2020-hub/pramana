"""Assignment + attempt + player HTTP router (the learner runtime).

Thin HTTP shell over :mod:`pramana.services.assignments` and
:mod:`pramana.services.player`. The request-scoped session
(:func:`~pramana.api.dependencies.get_db_session`) commits on success, so the
services never commit.

Two authorisation layers meet here. *Ownership* is enforced in the service —
a learner may only start, submit, watch, or read their own assignment. *Role*
is enforced at the router: assigning and cancelling require a manager or
compliance admin, and reading across users requires one of those or an auditor.
"""

from __future__ import annotations

import ipaddress
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api.dependencies import (
    forbid_cross_user_read,
    get_asset_signer,
    get_db_session,
    get_principal,
    may_read_others,
    require_roles,
)
from pramana.api.schemas import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentPage,
    AttemptOut,
    AttemptSubmitRequest,
    Pagination,
    PlayerManifestOut,
    ProgressUpdate,
    SubmissionResultOut,
    WatchProgressOut,
)
from pramana.db.models.identity import RoleName
from pramana.domain.assignment_state import utcnow
from pramana.domain.enums import AssignmentStatus
from pramana.services import assignments as svc
from pramana.services import player as player_svc
from pramana.services.auth import Principal
from pramana.services.player import AssetUrlSigner

router = APIRouter(prefix="/assignments", tags=["assignments"])


def _client_ip(request: Request) -> str | None:
    """The caller's IP, or ``None`` if it is absent or not a valid address.

    ``request.client.host`` can be a hostname (proxies, the test client), which
    the ``INET`` attestation column rejects — so we store only a real address.
    """
    host = request.client.host if request.client else None
    if host is None:
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None
    return host


Session = Annotated[AsyncSession, Depends(get_db_session)]
Caller = Annotated[Principal, Depends(get_principal)]

# Assigning and cancelling training are administrative acts; learners reach
# their own assignments through the self-scoped routes below.
_STAFF = require_roles(RoleName.MANAGER, RoleName.COMPLIANCE_ADMIN)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AssignmentOut,
    dependencies=[Depends(_STAFF)],
)
async def create_assignment(
    body: AssignmentCreate, session: Session, caller: Caller
) -> AssignmentOut:
    """Assign a course's active version to a user."""
    a = await svc.create_assignment(
        session,
        tenant_id=caller.tenant_id,
        user_id=body.user_id,
        course_id=body.course_id,
        assigned_by_user_id=caller.user_id,
        due_at=body.due_at,
        now=utcnow(),
    )
    return AssignmentOut.of(a)


@router.get("", response_model=AssignmentPage, dependencies=[Depends(forbid_cross_user_read)])
async def list_assignments(
    session: Session,
    caller: Caller,
    user_id: uuid.UUID | None = None,
    status_filter: Annotated[AssignmentStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AssignmentPage:
    """List assignments (tenant-wide for staff; the caller's own otherwise)."""
    scope = user_id if may_read_others(caller) else caller.user_id
    rows, total = await svc.list_assignments(
        session,
        tenant_id=caller.tenant_id,
        user_id=scope,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return AssignmentPage(
        items=[AssignmentOut.of(a) for a in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get("/me", response_model=AssignmentPage)
async def list_my_assignments(
    session: Session,
    caller: Caller,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AssignmentPage:
    """List the caller's own assignments."""
    rows, total = await svc.list_assignments(
        session,
        tenant_id=caller.tenant_id,
        user_id=caller.user_id,
        page=page,
        page_size=page_size,
    )
    return AssignmentPage(
        items=[AssignmentOut.of(a) for a in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get("/{assignment_id}", response_model=AssignmentOut)
async def get_assignment(
    assignment_id: uuid.UUID, session: Session, caller: Caller
) -> AssignmentOut:
    """Read one assignment — the caller's own, or any of them if staff."""
    a = await svc.get_assignment_for_reader(
        session,
        assignment_id=assignment_id,
        tenant_id=caller.tenant_id,
        acting_user_id=caller.user_id,
        may_read_others=may_read_others(caller),
    )
    return AssignmentOut.of(a)


@router.post(
    "/{assignment_id}/cancel", response_model=AssignmentOut, dependencies=[Depends(_STAFF)]
)
async def cancel_assignment(
    assignment_id: uuid.UUID, session: Session, caller: Caller
) -> AssignmentOut:
    a = await svc.cancel_assignment(
        session,
        assignment_id=assignment_id,
        tenant_id=caller.tenant_id,
        actor_user_id=caller.user_id,
        now=utcnow(),
    )
    return AssignmentOut.of(a)


@router.post(
    "/{assignment_id}/attempts", status_code=status.HTTP_201_CREATED, response_model=AttemptOut
)
async def start_attempt(assignment_id: uuid.UUID, session: Session, caller: Caller) -> AttemptOut:
    """Begin (or resume) an attempt for the caller's assignment."""
    attempt = await svc.start_attempt(
        session,
        assignment_id=assignment_id,
        tenant_id=caller.tenant_id,
        acting_user_id=caller.user_id,
        now=utcnow(),
    )
    return AttemptOut.of(attempt)


@router.post("/{assignment_id}/submit", response_model=SubmissionResultOut)
async def submit_attempt(
    assignment_id: uuid.UUID,
    body: AttemptSubmitRequest,
    request: Request,
    session: Session,
    caller: Caller,
) -> SubmissionResultOut:
    """Grade and submit the caller's in-progress attempt."""
    attestation = svc.Attestation(
        text_version=body.attestation.text_version,
        accepted=body.attestation.accepted,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    answers = {a.question_id: a.selected_option_ids for a in body.answers}
    result = await svc.submit_attempt(
        session,
        assignment_id=assignment_id,
        tenant_id=caller.tenant_id,
        acting_user_id=caller.user_id,
        answers=answers,
        attestation=attestation,
        now=utcnow(),
    )
    return SubmissionResultOut(
        assignment_id=assignment_id,
        status=result.snapshot.status.value,
        outcome=result.attempt.outcome,
        score_pct=result.grade.score_pct,
        retry_available=result.retry_available,
        remaining_attempts=result.snapshot.remaining_attempts,
        certificate_id=result.certificate.id if result.certificate is not None else None,
    )


@router.get("/{assignment_id}/player", response_model=PlayerManifestOut)
async def get_player(
    assignment_id: uuid.UUID,
    session: Session,
    caller: Caller,
    sign_asset: Annotated[AssetUrlSigner, Depends(get_asset_signer)],
) -> PlayerManifestOut:
    """Player manifest for the caller's pinned course version."""
    m = await player_svc.get_player_manifest(
        session,
        assignment_id=assignment_id,
        tenant_id=caller.tenant_id,
        acting_user_id=caller.user_id,
        sign_asset=sign_asset,
    )
    return PlayerManifestOut(
        assignment_id=m.assignment_id,
        course_version_id=m.course_version_id,
        status=m.status,
        video_url=m.video_url,
        min_watch_pct=m.min_watch_pct,
        watched_pct=m.watched_pct,
        quiz_unlocked=m.quiz_unlocked,
    )


@router.post("/{assignment_id}/progress", response_model=WatchProgressOut)
async def record_progress(
    assignment_id: uuid.UUID, body: ProgressUpdate, session: Session, caller: Caller
) -> WatchProgressOut:
    """Record the caller's watch progress (monotonic)."""
    p = await player_svc.record_progress(
        session,
        assignment_id=assignment_id,
        tenant_id=caller.tenant_id,
        acting_user_id=caller.user_id,
        watched_pct=body.watched_pct,
        now=utcnow(),
    )
    return WatchProgressOut(
        assignment_id=p.assignment_id,
        watched_pct=p.watched_pct,
        min_watch_pct=p.min_watch_pct,
        quiz_unlocked=p.quiz_unlocked,
    )
