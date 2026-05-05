"""Shared pytest fixtures.

Fixtures defined here are available to every test module without import.

Phase C provides only the foundational fixtures (settings overrides, factory
boy session). Database and HTTP-client fixtures are added in Phase B once the
SQLAlchemy models exist.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from pramana.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every test into the ``test`` environment with a deterministic secret.

    Runs automatically for every test. Prevents tests from accidentally reading
    the developer's local ``.env`` file or production credentials.
    """
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-for-production")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    # Clear the cached settings so the next call re-reads the env.
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Iterator[Settings]:
    """Return a fresh :class:`Settings` instance for the current test.

    Yields:
        A freshly parsed :class:`Settings`.
    """
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def anyio_backend() -> str:
    """Pin the anyio backend to asyncio for FastAPI test compatibility."""
    return "asyncio"


# --- Helpers --------------------------------------------------------------


def _ensure_test_environment() -> None:
    """Defensive guard: refuse to run tests against a non-test database.

    Imported and invoked by integration-test fixtures in later phases.
    """
    db_url = os.getenv("DATABASE_URL", "")
    if db_url and "test" not in db_url and "localhost" not in db_url:
        raise RuntimeError(
            "DATABASE_URL does not appear to point at a test database. "
            "Refusing to run tests to protect against data loss."
        )
