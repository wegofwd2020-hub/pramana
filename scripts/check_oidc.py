#!/usr/bin/env python3
"""Check an OIDC configuration against a real issuer, and optionally a real token.

Wiring an IdP fails in small, specific ways — a wrong audience, an issuer with a
trailing slash, a custom claim the provider silently dropped — and the symptom is
always the same opaque 401. This reports which step failed instead.

Run it before pointing a deployment at a new issuer::

    SSO_ISSUER_URL=https://your-tenant.auth0.com/ \\
    JWT_AUDIENCE=https://pramana.mambakkam.net/api \\
    SECRET_KEY=x python scripts/check_oidc.py

Add a real access token to check the whole path end to end::

    ... python scripts/check_oidc.py --token "$(cat token.txt)"

With a token it verifies the signature against the live JWKS, checks ``iss`` and
``aud``, and — the step that actually catches the Auth0 case — reports whether
the configured email claim is present. Auth0 access tokens do not carry ``email``
unless a post-login Action adds it as a *namespaced* claim, so a login that looks
correctly configured still fails at first bind without it.

Nothing here writes to the database or the audit log.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from pramana.config import get_settings
from pramana.services.auth import JwksKeySource, OidcJwtVerifier

OK = "  ok   "
BAD = " FAIL  "
WARN = " warn  "


async def _get_json(url: str) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data


def _line(state: str, label: str, detail: str = "") -> None:
    print(f"[{state}] {label}{(' — ' + detail) if detail else ''}")


async def _run(token: str | None) -> int:
    settings = get_settings()
    issuer = settings.sso_issuer_url.rstrip("/")
    audience = settings.jwt_audience
    email_claim = settings.oidc_email_claim
    failed = False

    print(f"issuer:      {issuer or '(unset)'}")
    print(f"audience:    {audience}")
    print(f"email claim: {email_claim}\n")

    if not issuer:
        _line(BAD, "SSO_ISSUER_URL is unset", "nothing to check")
        return 1

    # 1. Discovery.
    try:
        discovery = await _get_json(f"{issuer}/.well-known/openid-configuration")
        _line(OK, "OIDC discovery")
    except Exception as exc:
        _line(BAD, "OIDC discovery", f"{type(exc).__name__}: {exc}")
        return 1

    # The issuer the provider advertises must match what we validate against, or
    # every token fails `iss` verification for a reason nothing surfaces.
    advertised = str(discovery.get("issuer", "")).rstrip("/")
    if advertised != issuer:
        _line(BAD, "issuer mismatch", f"provider advertises {advertised!r}")
        failed = True
    else:
        _line(OK, "issuer matches the provider's own value")

    # 2. JWKS.
    try:
        jwks = await _get_json(discovery["jwks_uri"])
        kids = [k.get("kid") for k in jwks.get("keys", [])]
        _line(OK, "JWKS reachable", f"{len(kids)} key(s)")
    except Exception as exc:
        _line(BAD, "JWKS fetch", f"{type(exc).__name__}: {exc}")
        return 1

    if not token:
        _line(WARN, "no --token given", "signature, audience and claims unchecked")
        return 1 if failed else 0

    # 3. Verify the token exactly as the application does.
    verifier = OidcJwtVerifier(
        issuer=issuer,
        audience=audience,
        algorithms=[settings.jwt_algorithm],
        key_source=JwksKeySource(issuer, http_get_json=_get_json),
    )
    try:
        claims = await verifier.verify(token)
        _line(OK, "token verified", f"sub={claims.get('sub')!r}")
    except Exception as exc:
        _line(BAD, "token verification", str(exc))
        _line(
            WARN,
            "common causes",
            "audience differs from the API identifier; issuer trailing slash; expired token",
        )
        return 1

    # 4. The claim first-login actually needs.
    email = claims.get(email_claim)
    if isinstance(email, str) and email.strip():
        _line(OK, f"email claim {email_claim!r} present", email)
    else:
        failed = True
        _line(BAD, f"email claim {email_claim!r} missing")
        _line(
            WARN,
            "Auth0 note",
            "access tokens carry email only via a post-login Action, and the "
            "claim must be namespaced (https://your-domain/email)",
        )
        print("\n  present claims:", ", ".join(sorted(claims)))

    if claims.get("email_verified") is False:
        failed = True
        _line(BAD, "email_verified is false", "first-login provisioning refuses this")

    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", help="a real access token to verify end to end")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run(args.token))
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
