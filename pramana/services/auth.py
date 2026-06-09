"""OIDC bearer-token authentication.

Verifies the OIDC JWT presented as ``Authorization: Bearer <token>`` and resolves
it to a :class:`Principal` (the Pramana user + tenant). The signature is checked
against the issuer's JWKS; the ``sub`` claim is mapped to a provisioned ``User``
via :attr:`pramana.db.models.identity.User.sso_subject`.

The verification is isolated behind :class:`TokenVerifier` + :class:`KeySource`
so it is testable without a live IdP (tests inject a static key source).
Principal resolution first looks up the binding (``sub`` → ``User.sso_subject``);
on a first login with no binding yet it **provisions** by binding the ``sub`` to a
pre-provisioned user matched on the token's verified email. Binding only — a
token never *creates* a user; the account must already exist (e.g. from an HR
import), so an arbitrary valid token cannot mint access.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import structlog
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.db.models.identity import User, UserStatus
from pramana.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ExternalServiceError,
)
from pramana.services.audit import append_audit

logger = structlog.get_logger(__name__)

# Audit event recorded when a first login binds an SSO identity to a user — an
# access-control event for the SOX trail (who gained authenticated access, when).
FIRST_LOGIN_EVENT = "user.sso_bound"


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
async def resolve_principal(
    session: AsyncSession, claims: Mapping[str, Any], *, now: datetime
) -> Principal:
    """Map verified token claims to a :class:`Principal`.

    Resolves the existing ``sub`` → user binding; on a first login with no binding
    yet, provisions one via :func:`_provision_by_email` (which audits the bind).
    ``now`` stamps that audit entry.

    Raises:
        AuthenticationError: The token has no ``sub`` claim.
        AuthorizationError: No binding exists and none could be provisioned.
    """
    sub = claims.get("sub")
    if not sub:
        raise AuthenticationError("token is missing the 'sub' claim")
    user = (await session.execute(select(User).where(User.sso_subject == sub))).scalar_one_or_none()
    if user is None:
        user = await _provision_by_email(session, claims, sub=str(sub), now=now)
    return Principal(user_id=user.user_id, tenant_id=user.tenant_id)


async def _provision_by_email(
    session: AsyncSession, claims: Mapping[str, Any], *, sub: str, now: datetime
) -> User:
    """First login: bind ``sub`` to a pre-provisioned user matched on email.

    The user record must already exist with this email and no SSO binding yet;
    we attach the ``sub`` so subsequent logins take the fast binding path. This
    never creates a user — a valid token for an unknown email is rejected.

    Raises:
        AuthorizationError: No email claim, an unverified email, no unique email
            match, the matched user is already bound to a different identity, or
            it is not active.
    """
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise AuthorizationError(
            "no user is bound to this identity and the token carries no email to match it",
            context={"sub": sub},
        )
    email = email.strip()  # IdP claims may carry surrounding whitespace
    # The IdP signed the token, but only trust the email for *matching* if it
    # didn't explicitly mark it unverified.
    if claims.get("email_verified") is False:
        raise AuthorizationError("cannot provision from an unverified email", context={"sub": sub})

    matches = (
        (await session.execute(select(User).where(func.lower(User.email) == email.lower())))
        .scalars()
        .all()
    )
    if len(matches) != 1:
        # Zero → not pre-provisioned; more than one → ambiguous across tenants.
        raise AuthorizationError(
            "no unique Pramana user matches this identity",
            context={"sub": sub, "email_matches": len(matches)},
        )
    user = matches[0]
    if user.sso_subject is not None:
        raise AuthorizationError(
            "this user is already bound to a different SSO identity",
            context={"sub": sub},
        )
    if user.status != UserStatus.ACTIVE:
        raise AuthorizationError(
            "cannot provision a non-active user",
            context={"sub": sub, "status": user.status},
        )

    user.sso_subject = sub
    await session.flush()  # assign nothing new, but settle the bind before auditing
    await append_audit(
        session,
        tenant_id=user.tenant_id,
        actor_user_id=user.user_id,
        entity_type="user",
        entity_id=str(user.user_id),
        event_type=FIRST_LOGIN_EVENT,
        payload={"sub": sub},
        occurred_at=now,
    )
    logger.info(
        "auth.first_login_provisioned",
        user_id=str(user.user_id),
        tenant_id=str(user.tenant_id),
    )
    return user
