"""The seeded role set matches the roles the application enforces.

Roles are reference data with two homes, because the two ways a schema comes
into existence do not overlap: real deployments run Alembic, and the integration
suite builds tables straight from the ORM metadata. So migration ``0007`` seeds
for deployments and :func:`ensure_roles` seeds for tests and the bootstrap
script.

Duplication is acceptable only because this test makes the copies agree. If
someone adds a sixth role to :class:`RoleName`, both seeds must learn about it or
the suite fails here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from pramana.db.models.identity import RoleName
from pramana.services.roles import ROLE_DESCRIPTIONS

MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0007_seed_roles.py"


def _load_migration() -> ModuleType:
    """Import the migration by path (``alembic/versions`` is not a package)."""
    spec = importlib.util.spec_from_file_location("seed_roles_migration", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_seeds_every_role() -> None:
    """The migration's seed list covers exactly the roles RoleName defines."""
    seeded = {name for name, _description in _load_migration().SEEDED_ROLES}
    assert seeded == set(RoleName.values())


def test_ensure_roles_covers_every_role() -> None:
    """The runtime seed covers exactly the same set."""
    assert set(ROLE_DESCRIPTIONS) == set(RoleName.values())


def test_every_role_has_a_description() -> None:
    """A blank description would render an empty cell in any admin UI."""
    for name, description in _load_migration().SEEDED_ROLES:
        assert description.strip(), f"role {name!r} has no description"
