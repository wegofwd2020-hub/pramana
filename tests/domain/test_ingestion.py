"""Tests for the package → draft-fields mapping (Mentible ADR-011 §9.2)."""

from __future__ import annotations

import uuid

from pramana.domain.consumable_package import parse_manifest
from pramana.domain.enums import ContentDraftStatus
from pramana.domain.ingestion import package_to_draft_fields
from tests.support import make_signed_manifest


def _fields():
    pkg = parse_manifest(make_signed_manifest())
    tenant_id = uuid.uuid4()
    course_id = uuid.uuid4()
    return pkg, package_to_draft_fields(pkg, tenant_id=tenant_id, course_id=course_id)


def test_maps_to_received_status() -> None:
    _pkg, fields = _fields()
    assert fields.status is ContentDraftStatus.RECEIVED


def test_provenance_is_carried_through() -> None:
    pkg, fields = _fields()
    assert fields.gen_engine == pkg.provenance.engine == "mentible"
    assert fields.gen_model == pkg.provenance.model
    assert fields.gen_provider == pkg.provenance.provider
    assert fields.gen_prompt_version == pkg.provenance.prompt_version
    assert fields.generated_at == pkg.provenance.generated_at


def test_package_ref_and_hash_recorded() -> None:
    pkg, fields = _fields()
    assert fields.package_id == pkg.package_id
    assert fields.package_version == pkg.package_version
    assert fields.package_content_hash == pkg.declared_content_hash
    assert fields.signature == pkg.signature


def test_body_holds_content_verbatim() -> None:
    pkg, fields = _fields()
    assert fields.body["modules"] == [dict(m) for m in pkg.modules]
    assert fields.body["quiz"] == dict(pkg.quiz)
    assert "assets" in fields.body
    assert "artifacts" in fields.body


def test_source_definitions_become_citations() -> None:
    _pkg, fields = _fields()
    assert fields.source_citations[0]["framework"] == "sox"
    assert fields.source_citations[0]["clause"] == "404"


def test_as_model_kwargs_has_no_generator_user() -> None:
    _pkg, fields = _fields()
    kwargs = fields.as_model_kwargs()
    # External engine — no in-house generator user.
    assert "generated_by_user_id" not in kwargs
    assert kwargs["status"] == "received"
    assert kwargs["tenant_id"] == fields.tenant_id
