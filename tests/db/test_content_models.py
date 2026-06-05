"""Schema tests for the content-authoring models (no live Postgres needed)."""

from __future__ import annotations

from pramana.db.models import ContentDraft


def test_content_draft_table_name() -> None:
    assert ContentDraft.__tablename__ == "content_draft"


def test_content_draft_has_expected_columns() -> None:
    cols = set(ContentDraft.__table__.columns.keys())
    expected = {
        "id",
        "tenant_id",
        "course_id",
        "status",
        "title",
        "body",
        "source_citations",
        "gen_model",
        "gen_provider",
        "gen_prompt_version",
        "generated_at",
        "generated_by_user_id",
        "review_notes",
        "approved_by_user_id",
        "approved_at",
        "attestation_text",
        "content_hash",
        "published_course_version_id",
        "created_at",
        "updated_at",
        "archived_at",
    }
    assert expected <= cols, f"missing: {expected - cols}"


def test_content_draft_foreign_keys() -> None:
    fks = {
        f"{fk.parent.name}->{fk.column.table.name}.{fk.column.name}"
        for fk in ContentDraft.__table__.foreign_keys
    }
    assert "course_id->course.id" in fks
    assert "tenant_id->tenant.id" in fks
    assert "generated_by_user_id->user_account.user_id" in fks
    assert "approved_by_user_id->user_account.user_id" in fks
    assert "published_course_version_id->course_version.id" in fks


def test_content_draft_separation_of_duties_constraints_present() -> None:
    names = {c.name for c in ContentDraft.__table__.constraints}
    # The DB-level SoD + approval-pair guards back up the domain state machine.
    # (The metadata naming convention prefixes ck_content_draft_.)
    assert any("separation_of_duties" in n for n in names if n)
    assert any("approval_pair" in n for n in names if n)


def test_status_uses_named_enum() -> None:
    status_type = ContentDraft.__table__.columns["status"].type
    assert getattr(status_type, "name", None) == "content_draft_status"


def test_content_draft_has_ingestion_columns() -> None:
    cols = set(ContentDraft.__table__.columns.keys())
    ingestion = {
        "gen_engine",
        "package_id",
        "package_version",
        "package_content_hash",
        "signature",
    }
    assert ingestion <= cols, f"missing: {ingestion - cols}"


def test_content_draft_package_idempotency_index_is_unique_and_partial() -> None:
    idx = next(i for i in ContentDraft.__table__.indexes if i.name == "uq_content_draft_package")
    assert idx.unique
    assert [c.name for c in idx.columns] == [
        "tenant_id",
        "package_id",
        "package_version",
    ]
    # Partial: only enforced when the row is actually an ingested package.
    assert idx.dialect_options["postgresql"]["where"] is not None


def test_content_draft_package_ref_pair_constraint_present() -> None:
    names = {c.name for c in ContentDraft.__table__.constraints if c.name}
    assert any("package_ref_pair" in n for n in names)
