"""Tests for the consumer_library ingestion service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from pramana.db.models.content import ContentDraft
from pramana.exceptions import (
    DuplicatePackageError,
    NotFoundError,
    PackageIntegrityError,
    PackageValidationError,
)
from pramana.services.consumer_library import (
    ingest_consumable_package,
    verify_and_map,
)
from pramana.services.package_signing import HmacSignatureVerifier
from tests.support import DEFAULT_SECRET, make_signed_manifest

NOW = datetime(2026, 6, 5, 13, 0, tzinfo=timezone.utc)


@pytest.fixture
def verifier() -> HmacSignatureVerifier:
    return HmacSignatureVerifier(DEFAULT_SECRET)


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _session(*execute_results: object) -> AsyncMock:
    session = AsyncMock()
    session.execute.side_effect = list(execute_results)
    session.add = MagicMock()
    return session


# --- pure verify_and_map -------------------------------------------------
class TestVerifyAndMap:
    def test_valid_manifest_maps(self, verifier: HmacSignatureVerifier) -> None:
        fields = verify_and_map(
            make_signed_manifest(),
            tenant_id=uuid.uuid4(),
            course_id=uuid.uuid4(),
            verifier=verifier,
        )
        assert fields.status.value == "received"
        assert fields.gen_engine == "mentible"

    def test_invalid_manifest_raises(self, verifier: HmacSignatureVerifier) -> None:
        bad = make_signed_manifest()
        del bad["title"]
        with pytest.raises(PackageValidationError):
            verify_and_map(
                bad,
                tenant_id=uuid.uuid4(),
                course_id=uuid.uuid4(),
                verifier=verifier,
            )

    def test_tampered_manifest_quarantined(self, verifier: HmacSignatureVerifier) -> None:
        tampered = make_signed_manifest()
        tampered["modules"][0]["body_markdown"] = "tampered after signing"
        with pytest.raises(PackageIntegrityError):
            verify_and_map(
                tampered,
                tenant_id=uuid.uuid4(),
                course_id=uuid.uuid4(),
                verifier=verifier,
            )


# --- async orchestration (mocked session) --------------------------------
class TestIngestConsumablePackage:
    async def test_happy_path_creates_received_draft_and_audits(
        self, verifier: HmacSignatureVerifier
    ) -> None:
        tenant_id = uuid.uuid4()
        course_id = uuid.uuid4()
        # course lookup -> found; dup lookup -> none; audit head -> none
        session = _session(
            _scalar_result(course_id),
            _scalar_result(None),
            _scalar_result(None),
        )

        draft = await ingest_consumable_package(
            session,
            manifest=make_signed_manifest(),
            tenant_id=tenant_id,
            course_id=course_id,
            verifier=verifier,
            now=NOW,
        )

        assert isinstance(draft, ContentDraft)
        assert draft.status == "received"
        assert draft.tenant_id == tenant_id
        # draft added + audit entry added
        assert session.add.call_count == 2
        session.flush.assert_awaited_once()

    async def test_unknown_course_raises_not_found(self, verifier: HmacSignatureVerifier) -> None:
        session = _session(_scalar_result(None))
        with pytest.raises(NotFoundError):
            await ingest_consumable_package(
                session,
                manifest=make_signed_manifest(),
                tenant_id=uuid.uuid4(),
                course_id=uuid.uuid4(),
                verifier=verifier,
                now=NOW,
            )
        session.add.assert_not_called()

    async def test_duplicate_package_raises_conflict(self, verifier: HmacSignatureVerifier) -> None:
        course_id = uuid.uuid4()
        existing_draft_id = uuid.uuid4()
        session = _session(
            _scalar_result(course_id),
            _scalar_result(existing_draft_id),
        )
        with pytest.raises(DuplicatePackageError) as exc:
            await ingest_consumable_package(
                session,
                manifest=make_signed_manifest(),
                tenant_id=uuid.uuid4(),
                course_id=course_id,
                verifier=verifier,
                now=NOW,
            )
        assert exc.value.context["existing_draft_id"] == str(existing_draft_id)
        session.add.assert_not_called()

    async def test_quarantine_before_any_db_write(self, verifier: HmacSignatureVerifier) -> None:
        session = _session()
        tampered = make_signed_manifest()
        tampered["signature"] = "0" * 64
        with pytest.raises(PackageIntegrityError):
            await ingest_consumable_package(
                session,
                manifest=tampered,
                tenant_id=uuid.uuid4(),
                course_id=uuid.uuid4(),
                verifier=verifier,
                now=NOW,
            )
        session.execute.assert_not_called()
        session.add.assert_not_called()
