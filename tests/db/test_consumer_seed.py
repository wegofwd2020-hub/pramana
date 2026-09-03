"""The consumer-tenant seed constants agree between the migration and the service.

The consumer tenant has two homes because the two ways a schema comes into
existence do not overlap: real deployments run Alembic (migration ``0010``
seeds the row), and the integration suite builds tables straight from ORM
metadata and calls :func:`pramana.services.consumer_tenant.ensure_consumer_tenant`
instead.

Duplication is acceptable only because this test makes the copies agree.  If
someone renames the tenant's ``short_code`` or display name, both the migration
constant and the service constant must change, or the suite fails here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from pramana.services.consumer_tenant import (
    CONSUMER_TENANT_NAME,
    CONSUMER_TENANT_SHORT_CODE,
)

MIGRATION = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0010_consumer_subscription.py"
)


def _load_migration() -> ModuleType:
    """Import the migration by path (``alembic/versions`` is not a package)."""
    spec = importlib.util.spec_from_file_location("consumer_subscription_migration", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_short_code_agrees() -> None:
    """The migration and the service agree on the consumer tenant short_code."""
    migration = _load_migration()
    assert migration.CONSUMER_TENANT_SHORT_CODE == CONSUMER_TENANT_SHORT_CODE


def test_name_agrees() -> None:
    """The migration and the service agree on the consumer tenant display name."""
    migration = _load_migration()
    assert migration.CONSUMER_TENANT_NAME == CONSUMER_TENANT_NAME


def test_short_code_is_consumer() -> None:
    """The short_code is the literal string 'consumer' that queries depend on."""
    assert CONSUMER_TENANT_SHORT_CODE == "consumer"
