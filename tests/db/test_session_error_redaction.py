"""What an unexpected database failure is allowed to tell the caller.

Two places turn a raw driver failure into a :class:`DatabaseError`, and both
used to hand the driver's own text straight to the HTTP client:

- :func:`session_scope` interpolated ``{exc}`` into the message. SQLAlchemy's
  ``str()`` on a ``DBAPIError`` carries ``[SQL: ...]`` and
  ``[parameters: (...)]``, so a unique-constraint violation returned the
  statement and the bound values — emails, subject identifiers, names.
- :func:`get_engine` put ``settings.database_url`` into ``context``, which the
  API's error handler renders verbatim. That is the DSN, password included.

Both are CWE-209 (information exposure through an error message), and
SECURITY.md §3 says errors never leak secrets. The diagnostic detail is not
discarded — it goes to the log under an incident id that the caller is given,
so support can still answer "what actually happened" without the response body
carrying it.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from pramana.api.errors import register_exception_handlers
from pramana.config import get_settings
from pramana.db.session import get_engine, session_scope
from pramana.exceptions import DatabaseError

#: Values a hostile or merely curious caller must never read back out of an
#: error. These stand in for the PII that real bound parameters carry.
_EMAIL = "ceo@acme-client.example"
_SUBJECT = "auth0|64f1c0deadbeef"
_FULL_NAME = "Jane Doe"


def _driver_error() -> IntegrityError:
    """Build the error SQLAlchemy really raises on a unique violation."""
    orig = Exception(
        'duplicate key value violates unique constraint "user_email_key"\n'
        f"DETAIL:  Key (email)=({_EMAIL}) already exists."
    )
    return IntegrityError(
        statement='INSERT INTO "user" (email, sso_subject, full_name) VALUES ($1, $2, $3)',
        params=(_EMAIL, _SUBJECT, _FULL_NAME),
        orig=orig,
    )


class TestSessionScopeRedaction:
    """`session_scope` must not pass driver text through to the caller."""

    async def test_wrapped_driver_error_carries_no_sql_or_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The message names no statement and no bound value.

        Fails if the wrap goes back to interpolating ``{exc}``.
        """
        _use_fake_session(monkeypatch)

        with pytest.raises(DatabaseError) as ei:
            async with session_scope():
                raise _driver_error()

        message = ei.value.message
        assert "[SQL:" not in message
        assert "[parameters:" not in message
        for secret in (_EMAIL, _SUBJECT, _FULL_NAME, "user_email_key"):
            assert secret not in message

    async def test_wrapped_driver_error_carries_an_incident_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Redaction without a handle would make support impossible.

        The id is what ties the caller's report to the log line holding the
        detail that was withheld.
        """
        _use_fake_session(monkeypatch)

        with pytest.raises(DatabaseError) as ei:
            async with session_scope():
                raise _driver_error()

        assert isinstance(ei.value.incident_id, uuid.UUID)

    async def test_the_original_error_is_still_chained(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Redacting the response must not cost us the traceback.

        ``__cause__`` is how the detail reaches the log; dropping ``from exc``
        would make the incident id point at nothing.
        """
        _use_fake_session(monkeypatch)
        original = _driver_error()

        with pytest.raises(DatabaseError) as ei:
            async with session_scope():
                raise original

        assert ei.value.__cause__ is original

    async def test_application_errors_still_pass_through_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Redaction must not swallow our own typed errors.

        A 404 that came back as a redacted 502 would be a worse bug than the
        leak. This is the existing contract; it is pinned here because the
        redaction work touches the same except-chain.
        """
        from pramana.exceptions import NotFoundError

        _use_fake_session(monkeypatch)

        with pytest.raises(NotFoundError):
            async with session_scope():
                raise NotFoundError("course does not exist")


class TestEngineConstructionRedaction:
    """`get_engine` must not put the DSN anywhere the API can render it."""

    def test_bad_dsn_does_not_leak_the_password(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A malformed DSN is exactly when this fires, and the DSN holds a password."""
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql+nosuchdriver://pramana:SuperSecretPassw0rd@db.internal:5432/pramana",
        )
        get_settings.cache_clear()
        get_engine.cache_clear()

        with pytest.raises(DatabaseError) as ei:
            get_engine()

        rendered = f"{ei.value.message} {ei.value.context}"
        assert "SuperSecretPassw0rd" not in rendered
        assert "pramana:" not in rendered

        get_settings.cache_clear()
        get_engine.cache_clear()


class TestErrorResponseBody:
    """The end of the chain: what actually crosses the wire."""

    def test_database_error_body_contains_no_driver_detail(self) -> None:
        """An HTTP client sees a safe message and an incident id, nothing else."""
        app = FastAPI()
        register_exception_handlers(app)
        incident = uuid.uuid4()

        @app.get("/boom")
        async def boom() -> None:
            raise DatabaseError("A database operation failed.", incident_id=incident)

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/boom")

        assert response.status_code == 502
        body = response.text
        for secret in (_EMAIL, _SUBJECT, _FULL_NAME, "[SQL:", "[parameters:"):
            assert secret not in body
        assert response.json()["error"]["incident_id"] == str(incident)


def _use_fake_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point ``session_scope`` at a session that needs no database.

    The behaviour under test is the except-chain, not SQLAlchemy; a real engine
    would only add a connection this test does not need.
    """

    class _FakeSession:
        async def commit(self) -> None: ...

        async def rollback(self) -> None: ...

        async def close(self) -> None: ...

    monkeypatch.setattr("pramana.db.session.get_sessionmaker", lambda: lambda: _FakeSession())
