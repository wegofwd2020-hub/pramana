"""Liveness and readiness.

The two answer different questions and must not be conflated. ``/health`` asks
*is the process up* — an orchestrator restarts the container when it fails.
``/health/ready`` asks *can this instance serve a request* — an orchestrator
merely stops routing traffic when it fails. Wiring a restart to a database blip
would turn a brief outage into a crash loop.

``/health`` returned a constant and nothing verified anything, which is fine for
liveness and useless for readiness. The readiness tests below therefore include
the failing direction: a check that cannot fail is not a check.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from pramana.api.app import READINESS_TIMEOUT_SECONDS, create_app
from pramana.api.dependencies import get_db_session


def _client(session_override=None) -> TestClient:
    app = create_app()
    if session_override is not None:
        app.dependency_overrides[get_db_session] = session_override
    return TestClient(app)


class FakeSession:
    """Minimal stand-in: records the statement, raises, or hangs."""

    def __init__(self, *, fail: bool = False, hang_for: float | None = None) -> None:
        self.fail = fail
        self.hang_for = hang_for
        self.executed = False

    async def execute(self, statement: object) -> object:
        self.executed = True
        if self.hang_for is not None:
            await asyncio.sleep(self.hang_for)
        if self.fail:
            raise OSError("connection refused")
        return object()


class TestLiveness:
    def test_health_is_up_without_any_dependency(self) -> None:
        """Liveness must not depend on the database, or a blip causes a restart."""
        resp = _client().get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestReadiness:
    def test_ready_when_the_database_answers(self) -> None:
        session = FakeSession()

        async def _override():
            yield session

        resp = _client(_override).get("/health/ready")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ready", "database": "ok"}
        assert session.executed, "readiness did not actually query the database"

    def test_not_ready_when_the_database_is_unreachable(self) -> None:
        """The failing direction — without this the check proves nothing."""

        async def _override():
            yield FakeSession(fail=True)

        resp = _client(_override).get("/health/ready")

        assert resp.status_code == 503
        assert resp.json()["status"] == "not ready"

    def test_failure_does_not_leak_the_underlying_error(self) -> None:
        """A probe response is widely readable; connection strings are not."""

        async def _override():
            yield FakeSession(fail=True)

        body = _client(_override).get("/health/ready").text
        assert "connection refused" not in body

    def test_a_hanging_database_answers_503_rather_than_hanging(self) -> None:
        """A stopped database makes the driver wait, not refuse.

        Found in a container: with Postgres stopped rather than refusing, the
        probe timed out instead of getting a 503. A probe that hangs occupies a
        worker and delays the detection it exists to provide, so the query is
        bounded.
        """

        async def _override():
            yield FakeSession(hang_for=READINESS_TIMEOUT_SECONDS + 5)

        started = time.monotonic()
        resp = _client(_override).get("/health/ready")
        elapsed = time.monotonic() - started

        assert resp.status_code == 503
        assert elapsed < READINESS_TIMEOUT_SECONDS + 2, (
            f"readiness took {elapsed:.1f}s; it must be bounded by "
            f"READINESS_TIMEOUT_SECONDS ({READINESS_TIMEOUT_SECONDS}s)"
        )

    @pytest.mark.parametrize("path", ["/health", "/health/ready"])
    def test_neither_probe_requires_authentication(self, path: str) -> None:
        """An orchestrator has no bearer token."""
        assert _client().get(path).status_code in (200, 503)
