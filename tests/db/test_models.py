"""Tests for the SQLAlchemy schema metadata.

These tests verify that the model registrations are well-formed without
requiring a live Postgres connection. Tests that *do* require Postgres are
marked ``integration`` so they're skipped by default.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from pramana.db.base import Base
from pramana.db import models
from pramana.db.models import (
    AnswerOption,
    Assignment,
    Attempt,
    AttemptAnswer,
    AuditLog,
    Certificate,
    Course,
    CourseVersion,
    Question,
    Role,
    Tenant,
    User,
    UserRole,
)


EXPECTED_TABLES: set[str] = {
    "tenant",
    "user_account",
    "role",
    "user_role",
    "course",
    "course_version",
    "question",
    "answer_option",
    "assignment",
    "attempt",
    "attempt_answer",
    "certificate",
    "audit_log",
}


class TestMetadataRegistration:
    """Each entity in the resolved decisions doc has a corresponding table."""

    def test_all_expected_tables_registered(self) -> None:
        registered = set(Base.metadata.tables.keys())
        assert registered == EXPECTED_TABLES, (
            f"missing: {EXPECTED_TABLES - registered}, "
            f"extra: {registered - EXPECTED_TABLES}"
        )

    def test_models_module_exports_all_entities(self) -> None:
        """All entity classes are exposed via :mod:`pramana.db.models`."""
        for cls in (
            Tenant,
            User,
            Role,
            UserRole,
            Course,
            CourseVersion,
            Question,
            AnswerOption,
            Assignment,
            Attempt,
            AttemptAnswer,
            Certificate,
            AuditLog,
        ):
            assert cls.__name__ in models.__all__


class TestPrimaryKeys:
    """Every entity has the documented primary key column."""

    @pytest.mark.parametrize(
        ("model", "pk_name"),
        [
            (Tenant, "id"),
            (User, "user_id"),
            (Role, "id"),
            (UserRole, "id"),
            (Course, "id"),
            (CourseVersion, "id"),
            (Question, "id"),
            (AnswerOption, "id"),
            (Assignment, "id"),
            (Attempt, "id"),
            (AttemptAnswer, "id"),
            (Certificate, "id"),
            (AuditLog, "audit_id"),
        ],
    )
    def test_primary_key_column_present(
        self, model: type, pk_name: str
    ) -> None:
        pk_columns = inspect(model).primary_key
        assert len(pk_columns) == 1
        assert pk_columns[0].name == pk_name


class TestForeignKeys:
    """Critical foreign-key relationships exist with the right ON DELETE."""

    def test_user_tenant_fk_restrict(self) -> None:
        fk = next(
            fk for fk in User.__table__.foreign_keys
            if fk.column.table.name == "tenant"
        )
        assert fk.ondelete == "RESTRICT"

    def test_assignment_user_fk_restrict(self) -> None:
        """Assignments must not be silently deleted with a user (compliance)."""
        fk = next(
            fk for fk in Assignment.__table__.foreign_keys
            if fk.parent.name == "user_id"
        )
        assert fk.ondelete == "RESTRICT"

    def test_attempt_assignment_fk_cascade(self) -> None:
        """Cascading attempt deletion is fine — they're never deleted in practice."""
        fk = next(
            fk for fk in Attempt.__table__.foreign_keys
            if fk.parent.name == "assignment_id"
        )
        assert fk.ondelete == "CASCADE"

    def test_certificate_assignment_fk_restrict(self) -> None:
        fk = next(
            fk for fk in Certificate.__table__.foreign_keys
            if fk.parent.name == "assignment_id"
        )
        assert fk.ondelete == "RESTRICT"


class TestUniqueConstraints:
    """Documented uniqueness constraints are present."""

    def test_user_email_unique_per_tenant(self) -> None:
        constraint_names = {c.name for c in User.__table__.constraints}
        assert "user_tenant_email_unique" in constraint_names

    def test_attempt_number_unique_per_assignment(self) -> None:
        constraint_names = {c.name for c in Attempt.__table__.constraints}
        assert "attempt_number_unique" in constraint_names

    def test_attempt_answer_unique_per_question(self) -> None:
        constraint_names = {c.name for c in AttemptAnswer.__table__.constraints}
        assert "attempt_answer_unique" in constraint_names

    def test_certificate_assignment_unique(self) -> None:
        # One certificate per assignment.
        unique_columns = [
            c for c in Certificate.__table__.columns if c.unique
        ]
        assert any(c.name == "assignment_id" for c in unique_columns) or any(
            "assignment_id" in [col.name for col in c.columns]
            for c in Certificate.__table__.constraints
            if hasattr(c, "columns")
        )


class TestCheckConstraints:
    """Documented invariants are enforced at the schema level."""

    def test_assignment_terminal_at_consistency(self) -> None:
        names = {c.name for c in Assignment.__table__.constraints}
        assert "ck_assignment_terminal_at_consistent" in names

    def test_assignment_cooldown_until_consistency(self) -> None:
        names = {c.name for c in Assignment.__table__.constraints}
        assert "ck_assignment_cooldown_until_consistent" in names

    def test_attempt_score_pct_range(self) -> None:
        names = {c.name for c in Attempt.__table__.constraints}
        assert "ck_attempt_score_pct_range" in names

    def test_attempt_outcome_consistent_with_submission(self) -> None:
        names = {c.name for c in Attempt.__table__.constraints}
        assert "ck_attempt_outcome_consistent_with_submission" in names

    def test_user_pseudonymized_at_consistency(self) -> None:
        names = {c.name for c in User.__table__.constraints}
        assert "ck_user_account_pseudonymized_at_consistent" in names


class TestUserDisplayName:
    """The privacy-friendly display name."""

    def test_pseudonymized_user_returns_redacted(self) -> None:
        user = User(
            tenant_id=None,  # type: ignore[arg-type]
            email="x",
            first_name="John",
            last_name="Doe",
            user_type="employee",
            status="pseudonymized",
        )
        assert user.display_name == "[redacted]"

    def test_active_user_first_name_last_initial(self) -> None:
        user = User(
            tenant_id=None,  # type: ignore[arg-type]
            email="jdoe@example.com",
            first_name="Jane",
            last_name="Doe",
            user_type="employee",
            status="active",
        )
        assert user.display_name == "Jane D."

    def test_partial_name_handles_missing_last_name(self) -> None:
        user = User(
            tenant_id=None,  # type: ignore[arg-type]
            email="x",
            first_name="Cher",
            last_name=None,
            user_type="employee",
            status="active",
        )
        assert user.display_name == "Cher"


class TestEnumValues:
    """Enum value classes return the documented set."""

    def test_user_status_values(self) -> None:
        from pramana.db.models import UserStatus

        assert set(UserStatus.values()) == {
            "active",
            "inactive",
            "on_leave",
            "pseudonymized",
        }

    def test_role_name_values(self) -> None:
        from pramana.db.models import RoleName

        assert set(RoleName.values()) == {
            "trainee",
            "manager",
            "content_author",
            "compliance_admin",
            "auditor",
        }


class TestAlembicBaselineExists:
    """The Phase-B baseline migration file is present and parseable."""

    def test_baseline_revision_present(self) -> None:
        import importlib.util
        from pathlib import Path

        baseline = (
            Path(__file__).resolve().parents[2]
            / "alembic"
            / "versions"
            / "0001_initial.py"
        )
        assert baseline.exists(), "Baseline migration is missing"

        spec = importlib.util.spec_from_file_location("baseline", baseline)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.revision == "0001_initial"
        assert module.down_revision is None
        assert callable(module.upgrade)
        assert callable(module.downgrade)
