"""Tests for OIDC bearer-token authentication.

Verification is exercised with HS256 + a static key source (no IdP/network); the
RS256-vs-HS256 difference is only the key type — the claim/expiry/signature flow
is identical.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from jose import jwt

from pramana.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ExternalServiceError,
)
from pramana.services.auth import (
    JwksKeySource,
    OidcJwtVerifier,
    resolve_principal,
)

SECRET = "test-oidc-secret"
ISSUER = "https://idp.example.com"
AUD = "pramana"
NOW = datetime(2026, 6, 7, 14, 0, tzinfo=timezone.utc)


class StaticKeySource:
    def __init__(self, key: str = SECRET) -> None:
        self._key = key

    async def get(self, kid):
        return self._key


def make_token(*, secret=SECRET, aud=AUD, iss=ISSUER, sub="sub-123", exp_delta=3600):
    now = datetime.now(tz=timezone.utc)
    claims = {
        "sub": sub,
        "aud": aud,
        "iss": iss,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_delta)).timestamp()),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def verifier(*, secret=SECRET) -> OidcJwtVerifier:
    return OidcJwtVerifier(
        issuer=ISSUER,
        audience=AUD,
        algorithms=["HS256"],
        key_source=StaticKeySource(secret),
    )


class TestOidcJwtVerifier:
    async def test_valid_token_returns_claims(self) -> None:
        claims = await verifier().verify(make_token())
        assert claims["sub"] == "sub-123"

    async def test_expired_token_rejected(self) -> None:
        with pytest.raises(AuthenticationError, match="expired"):
            await verifier().verify(make_token(exp_delta=-30))

    async def test_wrong_audience_rejected(self) -> None:
        with pytest.raises(AuthenticationError):
            await verifier().verify(make_token(aud="another-app"))

    async def test_wrong_issuer_rejected(self) -> None:
        with pytest.raises(AuthenticationError):
            await verifier().verify(make_token(iss="https://evil.example.com"))

    async def test_bad_signature_rejected(self) -> None:
        with pytest.raises(AuthenticationError):
            await verifier().verify(make_token(secret="not-the-secret"))

    async def test_malformed_token_rejected(self) -> None:
        with pytest.raises(AuthenticationError, match="malformed"):
            await verifier().verify("definitely-not-a-jwt")


class TestResolvePrincipal:
    def _session(self, user) -> AsyncMock:
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        s = AsyncMock()
        s.execute = AsyncMock(return_value=result)
        return s

    async def test_known_user_resolves(self) -> None:
        user = MagicMock(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
        principal = await resolve_principal(self._session(user), {"sub": "sub-123"}, now=NOW)
        assert principal.user_id == user.user_id
        assert principal.tenant_id == user.tenant_id

    async def test_missing_sub_is_authentication_error(self) -> None:
        with pytest.raises(AuthenticationError, match="sub"):
            await resolve_principal(self._session(None), {}, now=NOW)

    async def test_unprovisioned_user_is_authorization_error(self) -> None:
        with pytest.raises(AuthorizationError):
            await resolve_principal(self._session(None), {"sub": "unknown"}, now=NOW)


class TestFirstLoginProvisioning:
    def _session(self, *, bound=None, email_matches=()) -> AsyncMock:
        bound_result = MagicMock()
        bound_result.scalar_one_or_none.return_value = bound
        email_result = MagicMock()
        email_result.scalars.return_value.all.return_value = list(email_matches)
        audit_result = MagicMock()  # append_audit's prev-hash lookup
        audit_result.scalar_one_or_none.return_value = None
        s = AsyncMock()
        s.execute = AsyncMock(side_effect=[bound_result, email_result, audit_result])
        s.add = MagicMock()
        s.flush = AsyncMock()
        return s

    async def test_binds_sub_to_matched_user(self) -> None:
        user = MagicMock(
            user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), sso_subject=None, status="active"
        )
        session = self._session(email_matches=[user])
        principal = await resolve_principal(
            session, {"sub": "new-sub", "email": "a@x.com"}, now=NOW
        )
        assert principal.user_id == user.user_id
        assert principal.tenant_id == user.tenant_id
        assert user.sso_subject == "new-sub"  # binding persisted on the row
        session.flush.assert_awaited_once()

    async def test_binding_writes_audit_entry(self) -> None:
        from pramana.db.models.audit import AuditLog
        from pramana.services.auth import FIRST_LOGIN_EVENT

        user = MagicMock(
            user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), sso_subject=None, status="active"
        )
        session = self._session(email_matches=[user])
        await resolve_principal(session, {"sub": "new-sub", "email": "a@x.com"}, now=NOW)
        added = [c.args[0] for c in session.add.call_args_list]
        entries = [a for a in added if isinstance(a, AuditLog)]
        assert len(entries) == 1
        entry = entries[0]
        assert entry.event_type == FIRST_LOGIN_EVENT
        assert entry.entity_type == "user"
        assert entry.entity_id == str(user.user_id)
        assert entry.actor_user_id == user.user_id
        assert entry.payload == {"sub": "new-sub"}
        assert entry.occurred_at == NOW

    async def test_mixed_case_email_still_provisions(self) -> None:
        user = MagicMock(
            user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), sso_subject=None, status="active"
        )
        session = self._session(email_matches=[user])
        await resolve_principal(session, {"sub": "s", "email": "MixedCase@X.com"}, now=NOW)
        assert user.sso_subject == "s"

    async def test_no_email_claim_rejected(self) -> None:
        with pytest.raises(AuthorizationError, match="email"):
            await resolve_principal(self._session(), {"sub": "s"}, now=NOW)

    async def test_unverified_email_rejected(self) -> None:
        with pytest.raises(AuthorizationError, match="unverified"):
            await resolve_principal(
                self._session(),
                {"sub": "s", "email": "a@x.com", "email_verified": False},
                now=NOW,
            )

    async def test_no_email_match_rejected(self) -> None:
        with pytest.raises(AuthorizationError):
            await resolve_principal(
                self._session(email_matches=[]), {"sub": "s", "email": "ghost@x.com"}, now=NOW
            )

    async def test_ambiguous_email_match_rejected(self) -> None:
        session = self._session(email_matches=[MagicMock(), MagicMock()])
        with pytest.raises(AuthorizationError):
            await resolve_principal(session, {"sub": "s", "email": "dup@x.com"}, now=NOW)

    async def test_already_bound_to_other_sub_rejected(self) -> None:
        user = MagicMock(sso_subject="some-other-sub", status="active")
        session = self._session(email_matches=[user])
        with pytest.raises(AuthorizationError, match="already bound"):
            await resolve_principal(session, {"sub": "s", "email": "a@x.com"}, now=NOW)

    async def test_non_active_user_not_provisioned(self) -> None:
        user = MagicMock(sso_subject=None, status="pseudonymized")
        session = self._session(email_matches=[user])
        with pytest.raises(AuthorizationError, match="non-active"):
            await resolve_principal(session, {"sub": "s", "email": "a@x.com"}, now=NOW)

    async def test_existing_binding_skips_provisioning(self) -> None:
        user = MagicMock(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)
        session.add = MagicMock()
        session.flush = AsyncMock()
        principal = await resolve_principal(session, {"sub": "bound", "email": "a@x.com"}, now=NOW)
        assert principal.user_id == user.user_id
        session.flush.assert_not_awaited()  # no write on the fast path
        session.add.assert_not_called()  # no audit on the fast path


class TestJwksKeySource:
    def _http(self, jwks):
        async def http_get_json(url):
            if "openid-configuration" in url:
                return {"jwks_uri": f"{ISSUER}/jwks"}
            return jwks

        return http_get_json

    async def test_fetches_discovery_then_selects_by_kid(self) -> None:
        src = JwksKeySource(
            ISSUER,
            http_get_json=self._http({"keys": [{"kid": "k1", "kty": "oct", "k": "x"}]}),
            monotonic=lambda: 0.0,
        )
        key = await src.get("k1")
        assert key["kid"] == "k1"

    async def test_unknown_kid_rejected(self) -> None:
        src = JwksKeySource(
            ISSUER,
            http_get_json=self._http({"keys": [{"kid": "k1"}]}),
            monotonic=lambda: 0.0,
        )
        with pytest.raises(AuthenticationError, match="signing key"):
            await src.get("missing")

    async def test_idp_failure_is_external_service_error(self) -> None:
        async def failing(url):
            raise RuntimeError("idp unreachable")

        src = JwksKeySource(ISSUER, http_get_json=failing, monotonic=lambda: 0.0)
        with pytest.raises(ExternalServiceError):
            await src.get("k1")

    async def test_unconfigured_issuer_rejected(self) -> None:
        src = JwksKeySource("", http_get_json=AsyncMock(), monotonic=lambda: 0.0)
        with pytest.raises(AuthenticationError, match="issuer"):
            await src.get("k1")


# --- dependency wiring (token extraction + get_principal) ----------------
import types  # noqa: E402

from pramana.api.dependencies import _bearer_token, get_principal  # noqa: E402


def fake_request(auth: str | None = None):
    headers = {} if auth is None else {"Authorization": auth}
    return types.SimpleNamespace(headers=headers)


class TestBearerExtraction:
    def test_missing_header_rejected(self) -> None:
        with pytest.raises(AuthenticationError, match="Authorization"):
            _bearer_token(fake_request())

    def test_non_bearer_scheme_rejected(self) -> None:
        with pytest.raises(AuthenticationError, match="Bearer"):
            _bearer_token(fake_request("Basic abc123"))

    def test_extracts_token(self) -> None:
        assert _bearer_token(fake_request("Bearer the.jwt.token")) == "the.jwt.token"


class TestGetPrincipalWiring:
    async def test_extract_verify_resolve(self) -> None:
        class FakeVerifier:
            async def verify(self, token):
                assert token == "tok"
                return {"sub": "sub-123"}

        user = MagicMock(user_id=uuid.uuid4(), tenant_id=uuid.uuid4())
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        principal = await get_principal(fake_request("Bearer tok"), FakeVerifier(), session)
        assert principal.user_id == user.user_id
        assert principal.tenant_id == user.tenant_id

    async def test_no_token_is_401(self) -> None:
        with pytest.raises(AuthenticationError):
            await get_principal(fake_request(), AsyncMock(), AsyncMock())
