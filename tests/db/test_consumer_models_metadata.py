"""Metadata-only checks — no database needed."""

import pramana.db.models  # noqa: F401  (ensure all models are registered)
from pramana.db.base import Base


def _table(name: str):
    return Base.metadata.tables[name]


def test_all_consumer_tables_registered():
    for name in [
        "package",
        "package_course",
        "entitlement",
        "enrollment",
        "play_session",
        "consumer_attempt",
        "consumer_attempt_answer",
    ]:
        assert name in Base.metadata.tables


def test_entitlement_has_partial_unique_active_index():
    ent = _table("entitlement")
    partials = [
        ix for ix in ent.indexes if ix.dialect_options["postgresql"].get("where") is not None
    ]
    cols = [sorted(c.name for c in ix.columns) for ix in partials]
    assert ["package_id", "user_id"] in cols


def test_enrollment_unique_user_course():
    enr = _table("enrollment")
    uniques = [
        tuple(sorted(c.name for c in con.columns))
        for con in enr.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("course_id", "user_id") in uniques


def test_consumer_attempt_score_check_present():
    ca = _table("consumer_attempt")
    check_names = [c.name for c in ca.constraints if c.__class__.__name__ == "CheckConstraint"]
    assert any("score_pct" in (n or "") for n in check_names)
