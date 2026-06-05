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
        principal = await resolve_principal(self._session(user), {"sub": "sub-123"})
        assert principal.user_id == user.user_id
        assert principal.tenant_id == user.tenant_id

    async def test_missing_sub_is_authentication_error(self) -> None:
        with pytest.raises(AuthenticationError, match="sub"):
            await resolve_principal(self._session(None), {})

    async def test_unprovisioned_user_is_authorization_error(self) -> None:
        with pytest.raises(AuthorizationError):
            await resolve_principal(self._session(None), {"sub": "unknown"})


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
