"""``session_scope`` must not reclassify the application's own errors.

The request-scoped session wraps its body in a transaction. Every route that
touches the database resolves its principal *inside* that scope, so an
``AuthenticationError`` / ``AuthorizationError`` / ``NotFoundError`` raised by a
dependency or handler propagates back out through ``session_scope``. If the
scope catches ``Exception`` broadly and re-raises ``DatabaseError``, a 401/403/
404 silently becomes a 502 ``database_error`` — the API's whole typed-exception
→ status mapping is defeated in production.

This is invisible to the rest of the suite because those tests override
``get_db_session`` with a plain session, bypassing ``session_scope`` entirely.
These use the real thing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pramana.api.app import create_app
from pramana.db.session import session_scope
from pramana.exceptions import AuthenticationError, DatabaseError, NotFoundError

pytestmark = pytest.mark.integration


class TestSessionScopePassesAppErrorsThrough:
    async def test_an_application_error_is_not_rewrapped_as_a_database_error(self) -> None:
        """The class must survive the scope so the HTTP layer can map it."""
        with pytest.raises(AuthenticationError):
            async with session_scope():
                raise AuthenticationError("missing Authorization header")

    async def test_a_not_found_is_not_rewrapped_either(self) -> None:
        with pytest.raises(NotFoundError):
            async with session_scope():
                raise NotFoundError("no such thing")

    async def test_a_genuine_error_still_becomes_a_database_error(self) -> None:
        """The wrapping is still wanted for unexpected, non-application failures."""
        with pytest.raises(DatabaseError):
            async with session_scope():
                raise RuntimeError("connection reset by peer")


class TestUnauthenticatedRequestStatus:
    def test_a_missing_token_is_401_not_502(self) -> None:
        """Through the real dependency chain (no session override), an
        unauthenticated privileged route must return 401, not a 502 that reads
        as a database outage."""
        client = TestClient(create_app())
        resp = client.get("/assignments")
        assert resp.status_code == 401, resp.text
        assert resp.json()["error"]["code"] == "authentication_required"
