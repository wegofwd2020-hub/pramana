"""Tests for the Consumable Package contract (Mentible ADR-011 §4 / §6)."""

from __future__ import annotations

import uuid
from datetime import UTC

import pytest

from pramana.domain.consumable_package import (
    SignatureVerifier,
    canonical_json,
    compute_content_hash,
    parse_manifest,
    verify_content_hash,
    verify_package,
    verify_signature,
)
from pramana.exceptions import PackageIntegrityError, PackageValidationError
from pramana.services.package_signing import HmacSignatureVerifier
from tests.support import DEFAULT_SECRET, make_manifest, make_signed_manifest


@pytest.fixture
def verifier() -> SignatureVerifier:
    return HmacSignatureVerifier(DEFAULT_SECRET)


class _AlwaysValid:
    def verify(self, *, signed_payload: bytes, signature: str) -> bool:
        return True


# --- parsing -------------------------------------------------------------
class TestParseManifest:
    def test_parses_a_well_formed_manifest(self) -> None:
        manifest = make_signed_manifest()
        pkg = parse_manifest(manifest)

        assert pkg.package_id == uuid.UUID(manifest["package_id"])
        assert pkg.package_version == 1
        assert pkg.title == manifest["title"]
        assert pkg.frameworks == ("sox",)
        assert pkg.source_definitions[0].clause == "404"
        assert pkg.provenance.engine == "mentible"
        assert pkg.provenance.generated_at.tzinfo == UTC
        assert len(pkg.modules) == 1
        assert pkg.quiz["pass_threshold_pct"] == 80

    def test_request_id_is_optional_and_defaults_none(self) -> None:
        pkg = parse_manifest(make_signed_manifest())
        assert pkg.request_id is None

    def test_request_id_parsed_when_echoed(self) -> None:
        rid = uuid.uuid4()
        pkg = parse_manifest(make_signed_manifest(request_id=str(rid)))
        assert pkg.request_id == rid

    def test_malformed_request_id_rejected(self) -> None:
        manifest = make_signed_manifest(request_id="not-a-uuid")
        with pytest.raises(PackageValidationError):
            parse_manifest(manifest)

    def test_rejects_non_object_manifest(self) -> None:
        with pytest.raises(PackageValidationError):
            parse_manifest([])  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "missing",
        [
            "package_id",
            "package_version",
            "title",
            "frameworks",
            "source_definitions",
            "provenance",
            "content_hash",
            "modules",
            "quiz",
            "signature",
        ],
    )
    def test_missing_required_field_is_rejected(self, missing: str) -> None:
        manifest = make_signed_manifest()
        del manifest[missing]
        with pytest.raises(PackageValidationError):
            parse_manifest(manifest)

    def test_empty_modules_rejected(self) -> None:
        manifest = make_signed_manifest(modules=[])
        with pytest.raises(PackageValidationError, match="modules"):
            parse_manifest(manifest)

    def test_empty_frameworks_rejected(self) -> None:
        manifest = make_signed_manifest(frameworks=[])
        with pytest.raises(PackageValidationError, match="frameworks"):
            parse_manifest(manifest)

    def test_bad_uuid_rejected(self) -> None:
        manifest = make_signed_manifest(package_id="not-a-uuid")
        with pytest.raises(PackageValidationError, match="UUID"):
            parse_manifest(manifest)

    def test_version_must_be_positive_int(self) -> None:
        with pytest.raises(PackageValidationError):
            parse_manifest(make_signed_manifest(package_version=0))

    def test_bool_is_not_accepted_as_int(self) -> None:
        with pytest.raises(PackageValidationError):
            parse_manifest(make_signed_manifest(package_version=True))

    def test_quiz_threshold_out_of_range_rejected(self) -> None:
        # Start signed (valid-format content_hash) then break the quiz; parse
        # checks hash *format* only, so it reaches the quiz validation.
        manifest = make_signed_manifest()
        manifest["quiz"]["pass_threshold_pct"] = 150
        with pytest.raises(PackageValidationError, match="pass_threshold_pct"):
            parse_manifest(manifest)

    def test_empty_quiz_questions_rejected(self) -> None:
        manifest = make_signed_manifest()
        manifest["quiz"]["questions"] = []
        with pytest.raises(PackageValidationError, match="questions"):
            parse_manifest(manifest)

    def test_naive_generated_at_rejected(self) -> None:
        manifest = make_signed_manifest()
        manifest["provenance"]["generated_at"] = "2026-06-05T12:00:00"
        with pytest.raises(PackageValidationError, match="timezone-aware"):
            parse_manifest(manifest)

    def test_malformed_content_hash_rejected(self) -> None:
        manifest = make_manifest()
        manifest["content_hash"] = "deadbeef"
        manifest["signature"] = "x"
        with pytest.raises(PackageValidationError, match="content_hash"):
            parse_manifest(manifest)

    def test_assets_and_artifacts_default_to_empty(self) -> None:
        manifest = make_signed_manifest()
        del manifest["assets"]
        del manifest["artifacts"]
        pkg = parse_manifest(manifest)
        assert pkg.assets == ()
        assert pkg.artifacts == ()


# --- canonicalisation + hashing ------------------------------------------
class TestCanonicalisation:
    def test_canonical_json_is_key_order_independent(self) -> None:
        assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})

    def test_content_hash_has_sha256_prefix(self) -> None:
        digest = compute_content_hash(b"hello")
        assert digest.startswith("sha256:")
        assert len(digest) == len("sha256:") + 64


# --- integrity verification ----------------------------------------------
class TestVerification:
    def test_valid_package_passes(self, verifier: SignatureVerifier) -> None:
        pkg = parse_manifest(make_signed_manifest())
        verify_package(pkg, verifier)  # no raise

    def test_content_hash_mismatch_quarantines(self) -> None:
        manifest = make_signed_manifest()
        # Tamper with the content after the hash was computed.
        manifest["modules"][0]["body_markdown"] = "tampered"
        pkg = parse_manifest(manifest)
        with pytest.raises(PackageIntegrityError, match="content_hash"):
            verify_content_hash(pkg)

    def test_bad_signature_quarantines(self, verifier: SignatureVerifier) -> None:
        manifest = make_signed_manifest()
        manifest["signature"] = "0" * 64
        pkg = parse_manifest(manifest)
        with pytest.raises(PackageIntegrityError, match="signature"):
            verify_signature(pkg, verifier)

    def test_wrong_secret_quarantines(self) -> None:
        pkg = parse_manifest(make_signed_manifest())
        with pytest.raises(PackageIntegrityError):
            verify_signature(pkg, HmacSignatureVerifier("a-different-secret"))

    def test_verify_package_checks_signature_first(self) -> None:
        # A package with a good signature but tampered content still fails (on hash).
        manifest = make_signed_manifest()
        pkg = parse_manifest(manifest)
        # Force a hash mismatch while keeping signature verification passing.
        object.__setattr__(pkg, "content_body_payload", b"different")
        with pytest.raises(PackageIntegrityError, match="content_hash"):
            verify_package(pkg, _AlwaysValid())


def test_hmac_verifier_rejects_empty_secret() -> None:
    with pytest.raises(ValueError, match="empty"):
        HmacSignatureVerifier("")
