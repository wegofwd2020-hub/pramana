"""The one place configuration reaches SQL as an identifier.

``GRANT``/``REVOKE`` cannot bind a role name as a parameter, so migration
``0009`` interpolates ``APP_DB_ROLE`` into the statement. Every other
interpolated identifier in the migrations is a module constant; this one comes
from the environment, which makes it the only injection-shaped surface in the
schema. ``tests/test_no_string_built_sql.py`` allow-lists that file on the
strength of the guard tested here, so if these tests go, the allow-list entry
is no longer justified.

The guard must *refuse*, not sanitise. Silently stripping a bad character would
apply grants to a role nobody named.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from pramana.config import get_settings

#: Loaded by path: "alembic/versions" is not a package and the file name starts
#: with a digit, so neither is importable by dotted name.
MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0009_audit_log_grants.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0009", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _app_role(monkeypatch: pytest.MonkeyPatch, value: str):
    monkeypatch.setenv("APP_DB_ROLE", value)
    get_settings.cache_clear()
    try:
        return _load_migration()._app_role()
    finally:
        get_settings.cache_clear()


class TestRejectsAnythingButAPlainIdentifier:
    @pytest.mark.parametrize(
        "hostile",
        [
            pytest.param("pramana_app; DROP TABLE audit_log; --", id="statement-break"),
            pytest.param('pramana_app"', id="double-quote"),
            pytest.param("pramana_app'", id="single-quote"),
            pytest.param("pramana-app", id="hyphen"),
            pytest.param("pramana app", id="space"),
            pytest.param("9lives", id="leading-digit"),
            pytest.param("public.pramana_app", id="dotted"),
            pytest.param("pramana_app\nGRANT ALL", id="newline"),
        ],
    )
    def test_hostile_role_names_raise(self, monkeypatch: pytest.MonkeyPatch, hostile: str) -> None:
        with pytest.raises(ValueError):
            _app_role(monkeypatch, hostile)

    def test_the_refusal_does_not_echo_the_value_into_a_statement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raising is the control; the message may name the value, not run it."""
        with pytest.raises(ValueError) as ei:
            _app_role(monkeypatch, "pramana_app; DROP TABLE audit_log; --")
        assert "refusing" in str(ei.value).lower()


class TestAcceptsWhatPostgresCallsAnIdentifier:
    @pytest.mark.parametrize("ok", ["pramana_app", "app", "_private", "Role9", "a_b_9"])
    def test_plain_identifiers_pass_through(self, monkeypatch: pytest.MonkeyPatch, ok: str) -> None:
        assert _app_role(monkeypatch, ok) == ok

    def test_unset_role_skips_rather_than_failing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Single-role deployments must still migrate.

        Returning None is what makes the grants opt-in; raising here would
        break every deployment that has not adopted the two-role topology.
        """
        assert _app_role(monkeypatch, "") is None

    def test_whitespace_only_is_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _app_role(monkeypatch, "   ") is None
