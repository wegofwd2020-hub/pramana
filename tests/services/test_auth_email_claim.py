"""Which claim carries the email at first login.

Auth0 access tokens for a custom API do **not** include ``email`` — that lives on
the ID token. An API access token carries ``iss``, ``sub``, ``aud``, ``iat``,
``exp``, ``scope``, ``azp``. Email has to be added by a post-login Action, and
Auth0 silently drops custom claims that are not namespaced, so it arrives as
something like ``https://pramana.mambakkam.net/email``.

Hardcoding ``email`` would therefore fail every first login against Auth0 with
"the token carries no email to match it" — and because users must be
pre-provisioned, nobody could ever bind. The claim name is configurable instead,
so a deployment names whatever its IdP actually sends.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pramana.exceptions import AuthorizationError
from pramana.services.auth import resolve_principal

NOW = datetime(2026, 9, 2, tzinfo=UTC)
NAMESPACED = "https://pramana.mambakkam.net/email"


def _session(*, email_matches=()) -> AsyncMock:
    bound = MagicMock()
    bound.scalar_one_or_none.return_value = None
    matched = MagicMock()
    matched.scalars.return_value.all.return_value = list(email_matches)
    audit = MagicMock()
    audit.scalar_one_or_none.return_value = None
    roles = MagicMock()
    roles.scalars.return_value.all.return_value = []
    s = AsyncMock()
    s.execute = AsyncMock(side_effect=[bound, matched, audit, roles])
    s.add = MagicMock()
    s.flush = AsyncMock()
    return s


def _user():
    return MagicMock(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), sso_subject=None, status="active"
    )


class TestConfigurableEmailClaim:
    async def test_default_still_reads_plain_email(self) -> None:
        """Unconfigured deployments keep working — this is not a breaking change."""
        user = _user()
        principal = await resolve_principal(
            _session(email_matches=[user]),
            {"sub": "new-sub", "email": "a@x.com"},
            now=NOW,
        )
        assert principal.user_id == user.user_id

    async def test_reads_a_namespaced_claim_when_configured(self) -> None:
        """The Auth0 shape: email arrives under a namespaced custom claim."""
        user = _user()
        principal = await resolve_principal(
            _session(email_matches=[user]),
            {"sub": "auth0|abc123", NAMESPACED: "a@x.com"},
            now=NOW,
            email_claim=NAMESPACED,
        )
        assert principal.user_id == user.user_id

    async def test_configured_claim_does_not_silently_fall_back(self) -> None:
        """A misconfigured Action must fail loudly, not resolve someone else.

        If the configured claim is absent, falling back to ``email`` would mean a
        deployment believing it reads a verified namespaced claim while actually
        trusting whatever else the token happens to carry.
        """
        with pytest.raises(AuthorizationError, match="email"):
            await resolve_principal(
                _session(email_matches=[_user()]),
                {"sub": "auth0|abc123", "email": "someone-else@x.com"},
                now=NOW,
                email_claim=NAMESPACED,
            )

    async def test_unverified_email_is_still_refused_under_a_custom_claim(self) -> None:
        """The email_verified guard must not be lost when the claim is renamed."""
        with pytest.raises(AuthorizationError):
            await resolve_principal(
                _session(email_matches=[_user()]),
                {"sub": "auth0|abc", NAMESPACED: "a@x.com", "email_verified": False},
                now=NOW,
                email_claim=NAMESPACED,
            )

    async def test_missing_claim_names_what_was_expected(self) -> None:
        """The operator debugging this needs to know which claim was looked for."""
        with pytest.raises(AuthorizationError) as exc:
            await resolve_principal(
                _session(), {"sub": "auth0|abc"}, now=NOW, email_claim=NAMESPACED
            )
        assert NAMESPACED in str(exc.value.context)
