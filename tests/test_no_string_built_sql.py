"""Keep SQL out of Python string building.

Every query in the application is a SQLAlchemy construct, so the values a
caller supplies are bound parameters and cannot become syntax. That is a
property of how the code is written today, not something the type checker or
the ORM enforces — one ``op.execute(f"... {user_input}")`` would end it, and
nothing would notice.

This module is that notice. It walks the source with :mod:`ast` and fails on
SQL assembled by f-string, ``+`` or ``.format()``.

**What it cannot do.** The allow-list below is per file, so an allowed file
could gain a genuinely unsafe line and still pass. That is a deliberate limit:
the entries are migrations interpolating *identifiers*, which cannot be bound
as parameters in ``GRANT``/``DROP``/``CREATE TRIGGER`` — there is no
parameterised form to prefer. Every entry interpolates a module-level constant
except ``0009``, which is the one place a value from configuration reaches SQL;
its guard is tested separately in ``tests/test_migration_identifier_guard.py``.
Adding a file here should be an argued decision, not a reflex.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCANNED_ROOTS = ("pramana", "scripts", "alembic")

#: Callables whose argument is SQL. ``op.execute`` is Alembic's, ``text`` is
#: SQLAlchemy's escape hatch, and ``exec_driver_sql`` bypasses the ORM entirely.
_SQL_SINKS = frozenset({"execute", "exec_driver_sql", "text", "executescript"})

#: file -> why its string-built SQL is safe. See the module docstring.
_ALLOWED: dict[str, str] = {
    "alembic/versions/0001_initial.py": (
        "DROP TYPE over a literal tuple of enum names defined in this module"
    ),
    "alembic/versions/0007_seed_roles.py": (
        "DELETE ... IN over names from the SEEDED_ROLES module constant"
    ),
    "alembic/versions/0009_audit_log_grants.py": (
        "GRANT/REVOKE cannot bind a role name; the identifier comes from "
        "APP_DB_ROLE and is rejected unless it matches ^[A-Za-z_][A-Za-z0-9_]*$ "
        "— see tests/test_migration_identifier_guard.py"
    ),
    "alembic/versions/0010_consumer_subscription.py": (
        "DROP TYPE over a literal list of enum names defined in this module"
    ),
    "alembic/versions/0011_audit_log_no_truncate.py": (
        "CREATE/DROP TRIGGER over table names from the _PROTECTED module constant"
    ),
}


def find_string_built_sql(source: str, path: str) -> list[tuple[str, int]]:
    """Return ``(path, lineno)`` for each SQL call built by string assembly.

    Args:
        source: Python source text.
        path: Repo-relative path, used only for the returned locations.

    Returns:
        One entry per offending call site, in source order.
    """
    hits: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not _is_sql_sink(node.func):
            continue
        for arg in node.args:
            if _is_assembled_string(arg):
                hits.append((path, node.lineno))
                break
    return hits


def _is_sql_sink(func: ast.expr) -> bool:
    if isinstance(func, ast.Attribute):
        return func.attr in _SQL_SINKS
    if isinstance(func, ast.Name):
        return func.id in _SQL_SINKS
    return False


def _is_assembled_string(node: ast.expr) -> bool:
    """True when the expression builds a string rather than being a literal."""
    if isinstance(node, ast.JoinedStr):  # f"..."
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"format", "join"}
    ):
        return True
    # sa.text(f"...") — the SQL sink wrapping another sink.
    if isinstance(node, ast.Call) and _is_sql_sink(node.func):
        return any(_is_assembled_string(inner) for inner in node.args)
    return False


class TestTheDetector:
    """The guard is worthless if it cannot see a violation, so prove it can."""

    @pytest.mark.parametrize(
        "snippet",
        [
            pytest.param('op.execute(f"GRANT ALL TO {role}")', id="f-string"),
            pytest.param('conn.execute("DELETE FROM t WHERE id = " + bad)', id="concat"),
            pytest.param('session.execute("SELECT {}".format(col))', id="format"),
            pytest.param('op.execute(sa.text(f"DROP TYPE {name}"))', id="wrapped-text"),
            pytest.param('cur.execute("SELECT %s" % value)', id="percent"),
        ],
    )
    def test_flags_sql_assembled_from_strings(self, snippet: str) -> None:
        assert find_string_built_sql(snippet, "x.py")

    @pytest.mark.parametrize(
        "snippet",
        [
            pytest.param("session.execute(select(User).where(User.id == uid))", id="orm"),
            pytest.param('session.execute(text("SELECT 1"))', id="constant-text"),
            pytest.param('logger.info(f"loaded {n} rows")', id="not-a-sql-sink"),
            pytest.param('path.read_text(encoding="utf-8")', id="read_text-is-not-sql"),
        ],
    )
    def test_leaves_parameterised_and_unrelated_calls_alone(self, snippet: str) -> None:
        assert not find_string_built_sql(snippet, "x.py")


class TestTheRepository:
    """The scan itself."""

    def test_no_unreviewed_string_built_sql(self) -> None:
        offenders = [(path, lineno) for path, lineno in _scan_repository() if path not in _ALLOWED]
        assert not offenders, (
            "SQL built by string assembly outside the reviewed allow-list:\n"
            + "\n".join(f"  {path}:{lineno}" for path, lineno in offenders)
            + "\n\nUse a SQLAlchemy construct so values bind as parameters. If the "
            "interpolated part is an identifier and genuinely cannot be bound, add "
            "the file to _ALLOWED with the reason."
        )

    def test_every_allow_list_entry_still_exists(self) -> None:
        """A stale entry silently widens the guard."""
        missing = [path for path in _ALLOWED if not (REPO_ROOT / path).is_file()]
        assert not missing, f"allow-listed files no longer present: {missing}"

    def test_every_allow_list_entry_is_still_needed(self) -> None:
        """An entry that no longer has string-built SQL should be deleted."""
        found = {path for path, _lineno in _scan_repository()}
        unnecessary = sorted(set(_ALLOWED) - found)
        assert not unnecessary, (
            f"these files no longer build SQL from strings; drop them from "
            f"_ALLOWED so the guard stays tight: {unnecessary}"
        )


def _scan_repository() -> list[tuple[str, int]]:
    hits: list[tuple[str, int]] = []
    for root in SCANNED_ROOTS:
        for file in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = file.relative_to(REPO_ROOT).as_posix()
            hits.extend(find_string_built_sql(file.read_text(encoding="utf-8"), rel))
    return hits
