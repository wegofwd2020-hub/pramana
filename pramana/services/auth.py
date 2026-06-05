"""OIDC bearer-token authentication.

Verifies the OIDC JWT presented as ``Authorization: Bearer <token>`` and resolves
it to a :class:`Principal` (the Pramana user + tenant). The signature is checked
against the issuer's JWKS; the ``sub`` claim is mapped to a provisioned ``User``
via :attr:`pramana.db.models.identity.User.sso_subject`.

The verification is isolated behind :class:`TokenVerifier` + :class:`KeySource`
so it is testable without a live IdP (tests inject a static key source); the
principal resolution is a plain query. First-login provisioning (binding a new
``sub`` to a user by email) is a deliberate follow-up — this resolves an existing
binding only.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.identity import User
from pramana.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ExternalServiceError,
)


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller: their Pramana ``user_id`` and ``tenant_id``."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
class KeySource(Protocol):
    """Supplies the signing key for a token's ``kid`` (the JWKS, abstracted)."""

    async def get(self, kid: str | None) -> Any: ...


class TokenVerifier(Protocol):
    """Verifies a bearer token and returns its validated claims."""

    async def verify(self, token: str) -> Mapping[str, Any]: ...


class OidcJwtVerifier:
    """Verifies an OIDC JWT (signature + ``iss``/``aud``/``exp``) via a key source.

    Algorithm-agnostic: production uses ``RS256`` against the issuer JWKS; tests
    can use a static key source. Any verification failure surfaces as
    :class:`~pramana.exceptions.AuthenticationError`.
    """

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        algorithms: list[str],
        key_source: KeySource,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._algorithms = list(algorithms)
        self._key_source = key_source

    async def verify(self, token: str) -> Mapping[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except JWTError as exc:
            raise AuthenticationError("malformed bearer token") from exc
        key = await self._key_source.get(header.get("kid"))
        try:
            return jwt.decode(
                token,
                key,
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
            )
        except ExpiredSignatureError as exc:
            raise AuthenticationError("token has expired") from exc
        except (JWTClaimsError, JWTError) as exc:
            raise AuthenticationError(
                "token verification failed", context={"reason": str(exc)}
            ) from exc


class JwksKeySource:
    """Fetches and caches the issuer's JWKS via OIDC discovery.

    Refreshes when the cache is empty or a presented ``kid`` is unknown (picking
    up key rotation), throttled to at most once per ``min_refresh_seconds`` so an
    unknown ``kid`` cannot hammer the IdP.
    """

    def __init__(
        self,
        issuer: str,
        *,
        http_get_json: Callable[[str], Awaitable[Mapping[str, Any]]],
        min_refresh_seconds: float = 60.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._http_get_json = http_get_json
        self._min_refresh = min_refresh_seconds
        self._monotonic = monotonic
        self._by_kid: dict[str, Any] = {}
        self._last_refresh: float | None = None

    async def get(self, kid: str | None) -> Any:
        if (kid is None or kid not in self._by_kid) and self._should_refresh():
            await self._refresh()
        key = self._by_kid.get(kid) if kid is not None else next(iter(self._by_kid.values()), None)
        if key is None:
            raise AuthenticationError("no matching JWKS signing key", context={"kid": kid})
        return key

    def _should_refresh(self) -> bool:
        if not self._by_kid or self._last_refresh is None:
            return True
        return (self._monotonic() - self._last_refresh) >= self._min_refresh

    async def _refresh(self) -> None:
        if not self._issuer:
            raise AuthenticationError("OIDC issuer is not configured")
        try:
            discovery = await self._http_get_json(
                f"{self._issuer}/.well-known/openid-configuration"
            )
            jwks = await self._http_get_json(discovery["jwks_uri"])
        except Exception as exc:  # surface any IdP/transport failure as downstream
            raise ExternalServiceError(
                "failed to fetch the IdP JWKS", context={"issuer": self._issuer}
            ) from exc
        self._by_kid = {k["kid"]: k for k in jwks.get("keys", []) if "kid" in k}
        self._last_refresh = self._monotonic()


# ---------------------------------------------------------------------------
# Principal resolution
# ---------------------------------------------------------------------------
async def resolve_principal(session: AsyncSession, claims: Mapping[str, Any]) -> Principal:
    """Map verified token claims to a :class:`Principal`.

    Raises:
        AuthenticationError: The token has no ``sub`` claim.
        AuthorizationError: No Pramana user is bound to this ``sub``.
    """
    sub = claims.get("sub")
    if not sub:
        raise AuthenticationError("token is missing the 'sub' claim")
    user = (await session.execute(select(User).where(User.sso_subject == sub))).scalar_one_or_none()
    if user is None:
        raise AuthorizationError(
            "no Pramana user is bound to this identity",
            context={"sub": str(sub)},
        )
    return Principal(user_id=user.user_id, tenant_id=user.tenant_id)
