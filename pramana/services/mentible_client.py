"""Outbound transport to Mentible — pushing a Package Request (the Create side).

ADR-011's handoff is an artifact exchange: Pramana pushes a Package Request and,
later, Mentible pushes back a signed Consumable Package (handled inbound by
:mod:`pramana.services.consumer_library`). This module is the **outbound** port.

It is a thin seam, deliberately: the concrete Mentible request endpoint and its
auth are not yet specified (ADR-011 §4 fixes the *payload*, not the URL), so the
service depends on the :class:`MentibleClient` protocol and the default
implementation is chosen by configuration. When ``mentible_request_url`` is unset
(dev/test) the default is :class:`NullMentibleClient`, which records the push
without performing network I/O; production wires a real HTTP client against the
same protocol without touching the service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import structlog

from pramana.exceptions import ExternalServiceError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PushResult:
    """Mentible's acknowledgement of an accepted request.

    ``accepted`` is the happy path; ``package_id`` may be echoed back if Mentible
    assigns it synchronously, otherwise it arrives later on the inbound package.
    """

    accepted: bool
    package_id: str | None = None
    detail: str | None = None


@runtime_checkable
class MentibleClient(Protocol):
    """Pushes a Package Request payload to Mentible."""

    async def push_request(self, payload: dict[str, Any]) -> PushResult:
        """Submit a request; raise :class:`ExternalServiceError` on transport failure."""
        ...


class NullMentibleClient:
    """Default client: records the push, performs no network I/O.

    Used until a real Mentible request endpoint is configured. The request is
    persisted as ``requested`` regardless; this only stands in for the wire call,
    so commissioning is fully exercisable end-to-end without Mentible present.
    """

    async def push_request(self, payload: dict[str, Any]) -> PushResult:
        logger.info(
            "mentible.push_request.stubbed",
            request_id=payload.get("request_id"),
            framework=payload.get("framework"),
        )
        return PushResult(accepted=True, detail="recorded (no Mentible endpoint configured)")


@dataclass(slots=True)
class HttpMentibleClient:
    """HTTP client that POSTs the request payload to Mentible's endpoint.

    Kept minimal — auth/retry policy is layered in when the endpoint contract is
    finalized. A non-2xx or transport error surfaces as
    :class:`~pramana.exceptions.ExternalServiceError` so the service marks the
    request ``failed`` rather than silently dropping it.
    """

    url: str
    timeout: float = 10.0

    async def push_request(self, payload: dict[str, Any]) -> PushResult:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.url, json=payload)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "failed to push Package Request to Mentible",
                context={"url": self.url, "error": str(exc)},
            ) from exc
        return PushResult(
            accepted=True,
            package_id=data.get("package_id"),
            detail=data.get("detail"),
        )
