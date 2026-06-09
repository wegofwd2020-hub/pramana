"""Tests for the content-request (commission) service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from pramana.db.models.content import ContentDraft
from pramana.db.models.content_request import ContentRequest
from pramana.domain.enums import ContentRequestStatus
from pramana.exceptions import ExternalServiceError, NotFoundError, ValidationError
from pramana.services import content_requests as crq
from pramana.services.mentible_client import PushResult

NOW = datetime(2026, 6, 7, 14, 0, tzinfo=UTC)
TENANT = uuid.uuid4()
USER = uuid.uuid4()

_FCPA_DOC = "# Framework Reference: FCPA\n\n### Anti-bribery\nText.\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "framework_fcpa.md").write_text(_FCPA_DOC, encoding="utf-8")
    return tmp_path


def _body(**overrides) -> dict:
    body = {
        "framework": "fcpa",
        "title": "FCPA Anti-Bribery",
        "source_definitions": [
            {
                "framework": "fcpa",
                "clause": "anti-bribery",
                "ref": "docs/frameworks/framework_fcpa.md#anti-bribery",
            }
        ],
        "assessment": {"pass_threshold_pct": 80},
    }
    body.update(overrides)
    return body


def _result(*, scalar=None, rows=()) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalar_one.return_value = scalar if scalar is not None else 0
    r.scalars.return_value.all.return_value = list(rows)
    return r


def fake_session(*, get=None, execute=None) -> AsyncMock:
    s = AsyncMock()
    s.get = AsyncMock(return_value=get)
    s.execute = (
        AsyncMock(side_effect=execute) if execute is not None else AsyncMock(return_value=_result())
    )
    s.add = MagicMock()
    s.flush = AsyncMock()
    return s


class FakeMentible:
    def __init__(self, *, result=None, raises=None):
        self.result = result or PushResult(accepted=True)
        self.raises = raises
        self.pushed: list[dict] = []

    async def push_request(self, payload):
        self.pushed.append(payload)
        if self.raises is not None:
            raise self.raises
        return self.result


class TestCommission:
    async def test_commissions_and_pushes(self, root: Path) -> None:
        session = fake_session(execute=[_result()])  # audit prev-hash lookup
        mentible = FakeMentible()
        cr = await crq.commission_request(
            session,
            body=_body(),
            tenant_id=TENANT,
            requested_by=USER,
            definitions_root=root,
            mentible=mentible,
            now=NOW,
        )
        assert isinstance(cr, ContentRequest)
        assert cr.status == ContentRequestStatus.REQUESTED.value
        assert cr.framework == "fcpa"
        assert cr.requested_by == USER
        assert cr.spec["request_id"] == str(cr.id)
        assert cr.spec["requested_by"] == str(USER)
        assert len(mentible.pushed) == 1
        # request row + audit entry both added
        assert session.add.call_count >= 2

    async def test_unresolvable_clause_is_rejected_before_push(self, root: Path) -> None:
        session = fake_session()
        mentible = FakeMentible()
        body = _body(
            source_definitions=[
                {
                    "framework": "fcpa",
                    "clause": "ghost",
                    "ref": "docs/frameworks/framework_fcpa.md#ghost",
                }
            ]
        )
        with pytest.raises(ValidationError):
            await crq.commission_request(
                session,
                body=body,
                tenant_id=TENANT,
                requested_by=USER,
                definitions_root=root,
                mentible=mentible,
                now=NOW,
            )
        assert mentible.pushed == []
        session.add.assert_not_called()

    async def test_malformed_request_is_rejected(self, root: Path) -> None:
        session = fake_session()
        with pytest.raises(ValidationError):
            await crq.commission_request(
                session,
                body={"framework": "fcpa"},
                tenant_id=TENANT,
                requested_by=USER,
                definitions_root=root,
                mentible=FakeMentible(),
                now=NOW,
            )

    async def test_push_rejection_raises(self, root: Path) -> None:
        session = fake_session()
        mentible = FakeMentible(result=PushResult(accepted=False, detail="nope"))
        with pytest.raises(ExternalServiceError):
            await crq.commission_request(
                session,
                body=_body(),
                tenant_id=TENANT,
                requested_by=USER,
                definitions_root=root,
                mentible=mentible,
                now=NOW,
            )

    async def test_push_transport_error_propagates(self, root: Path) -> None:
        session = fake_session()
        mentible = FakeMentible(raises=ExternalServiceError("boom"))
        with pytest.raises(ExternalServiceError):
            await crq.commission_request(
                session,
                body=_body(),
                tenant_id=TENANT,
                requested_by=USER,
                definitions_root=root,
                mentible=mentible,
                now=NOW,
            )

    async def test_synchronous_package_id_recorded(self, root: Path) -> None:
        pkg = uuid.uuid4()
        session = fake_session(execute=[_result()])
        mentible = FakeMentible(result=PushResult(accepted=True, package_id=str(pkg)))
        cr = await crq.commission_request(
            session,
            body=_body(),
            tenant_id=TENANT,
            requested_by=USER,
            definitions_root=root,
            mentible=mentible,
            now=NOW,
        )
        assert cr.package_id == pkg


class TestRegenerate:
    def _draft(self) -> ContentDraft:
        d = ContentDraft(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            course_id=uuid.uuid4(),
            status="published",
            title="FCPA Anti-Bribery",
            body={"quiz": {"pass_threshold_pct": 80, "questions": [1]}},
            source_citations=[
                {
                    "framework": "fcpa",
                    "clause": "anti-bribery",
                    "ref": "docs/frameworks/framework_fcpa.md#anti-bribery",
                }
            ],
            package_id=uuid.uuid4(),
            package_version=1,
        )
        d.archived_at = None
        return d

    async def test_regenerates_from_reconstructed_spec(self, root: Path) -> None:
        draft = self._draft()
        # execute: originating-request lookup (None) then audit prev-hash
        session = fake_session(get=draft, execute=[_result(scalar=None), _result()])
        mentible = FakeMentible()
        cr = await crq.regenerate_from_draft(
            session,
            draft_id=draft.id,
            tenant_id=TENANT,
            requested_by=USER,
            parameter_overrides=None,
            definitions_root=root,
            mentible=mentible,
            now=NOW,
        )
        assert cr.regenerated_from_draft_id == draft.id
        assert cr.course_id == draft.course_id
        assert cr.framework == "fcpa"
        assert len(mentible.pushed) == 1

    async def test_overrides_merge_into_spec(self, root: Path) -> None:
        draft = self._draft()
        session = fake_session(get=draft, execute=[_result(scalar=None), _result()])
        mentible = FakeMentible()
        cr = await crq.regenerate_from_draft(
            session,
            draft_id=draft.id,
            tenant_id=TENANT,
            requested_by=USER,
            parameter_overrides={"title": "Revised Title"},
            definitions_root=root,
            mentible=mentible,
            now=NOW,
        )
        assert cr.title == "Revised Title"

    async def test_missing_draft_404(self, root: Path) -> None:
        session = fake_session(get=None)
        with pytest.raises(NotFoundError):
            await crq.regenerate_from_draft(
                session,
                draft_id=uuid.uuid4(),
                tenant_id=TENANT,
                requested_by=USER,
                parameter_overrides=None,
                definitions_root=root,
                mentible=FakeMentible(),
                now=NOW,
            )

    async def test_cross_tenant_draft_404(self, root: Path) -> None:
        draft = self._draft()
        draft.tenant_id = uuid.uuid4()  # different tenant
        session = fake_session(get=draft)
        with pytest.raises(NotFoundError):
            await crq.regenerate_from_draft(
                session,
                draft_id=draft.id,
                tenant_id=TENANT,
                requested_by=USER,
                parameter_overrides=None,
                definitions_root=root,
                mentible=FakeMentible(),
                now=NOW,
            )


class TestListAndGet:
    async def test_list_returns_items_and_total(self) -> None:
        cr = ContentRequest(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            framework="fcpa",
            title="t",
            status="requested",
            requested_by=USER,
            spec={},
        )
        session = fake_session(execute=[_result(scalar=1), _result(rows=[cr])])
        items, total = await crq.list_requests(session, tenant_id=TENANT)
        assert total == 1
        assert list(items) == [cr]

    async def test_get_missing_404(self) -> None:
        session = fake_session(get=None)
        with pytest.raises(NotFoundError):
            await crq.get_request(session, request_id=uuid.uuid4(), tenant_id=TENANT)


def _request(status: str = "requested") -> ContentRequest:
    cr = ContentRequest(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        framework="fcpa",
        title="t",
        status=status,
        requested_by=USER,
        spec={},
    )
    cr.course_id = cr.package_id = cr.draft_id = cr.regenerated_from_draft_id = None
    cr.archived_at = None
    return cr


class TestLinkReceivedPackage:
    async def test_links_and_advances_to_received(self) -> None:
        cr = _request("requested")
        draft_id, pkg_id = uuid.uuid4(), uuid.uuid4()
        session = fake_session(get=cr, execute=[_result()])  # audit prev-hash
        out = await crq.link_received_package(
            session,
            request_id=cr.id,
            tenant_id=TENANT,
            draft_id=draft_id,
            package_id=pkg_id,
            now=NOW,
        )
        assert out is cr
        assert cr.status == ContentRequestStatus.RECEIVED.value
        assert cr.draft_id == draft_id
        assert cr.package_id == pkg_id

    async def test_noop_when_request_missing(self) -> None:
        session = fake_session(get=None)
        out = await crq.link_received_package(
            session,
            request_id=uuid.uuid4(),
            tenant_id=TENANT,
            draft_id=uuid.uuid4(),
            package_id=uuid.uuid4(),
            now=NOW,
        )
        assert out is None
        session.add.assert_not_called()

    async def test_noop_when_already_past_requested(self) -> None:
        cr = _request("published")
        session = fake_session(get=cr)
        out = await crq.link_received_package(
            session,
            request_id=cr.id,
            tenant_id=TENANT,
            draft_id=uuid.uuid4(),
            package_id=uuid.uuid4(),
            now=NOW,
        )
        assert out is None
        assert cr.status == "published"

    async def test_noop_cross_tenant(self) -> None:
        cr = _request("requested")
        cr.tenant_id = uuid.uuid4()
        session = fake_session(get=cr)
        out = await crq.link_received_package(
            session,
            request_id=cr.id,
            tenant_id=TENANT,
            draft_id=uuid.uuid4(),
            package_id=uuid.uuid4(),
            now=NOW,
        )
        assert out is None


class TestAdvanceForDraft:
    async def test_advances_linked_request(self) -> None:
        cr = _request("received")
        draft_id = uuid.uuid4()
        cr.draft_id = draft_id
        session = fake_session(execute=[_result(scalar=cr), _result()])
        out = await crq.advance_for_draft(
            session,
            draft_id=draft_id,
            tenant_id=TENANT,
            status=ContentRequestStatus.PUBLISHED,
            now=NOW,
        )
        assert out is cr
        assert cr.status == ContentRequestStatus.PUBLISHED.value

    async def test_noop_when_no_linked_request(self) -> None:
        session = fake_session(execute=[_result(scalar=None)])
        out = await crq.advance_for_draft(
            session,
            draft_id=uuid.uuid4(),
            tenant_id=TENANT,
            status=ContentRequestStatus.IN_REVIEW,
            now=NOW,
        )
        assert out is None

    async def test_does_not_regress_terminal_request(self) -> None:
        cr = _request("published")
        cr.draft_id = uuid.uuid4()
        session = fake_session(execute=[_result(scalar=cr)])
        out = await crq.advance_for_draft(
            session,
            draft_id=cr.draft_id,
            tenant_id=TENANT,
            status=ContentRequestStatus.IN_REVIEW,
            now=NOW,
        )
        assert out is None
        assert cr.status == "published"


def test_parse_status_rejects_unknown() -> None:
    from pramana.exceptions import InvalidStateTransitionError

    with pytest.raises(InvalidStateTransitionError):
        crq.parse_status("bogus")
