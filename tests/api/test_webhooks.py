"""HTTP-layer tests for the inbound Mentible progress webhook.

The signature verifier and webhook handler seams are overridden, so these
exercise HMAC authentication, body parsing, and status mapping without a
database. Signatures are computed over the exact bytes posted.
"""

from __future__ import annotations

import hmac
import json
import uuid
from collections.abc import Iterator
from hashlib import sha256

from fastapi.testclient import TestClient

from pramana.api.app import create_app
from pramana.api.dependencies import (
    get_mentible_webhook_handler,
    get_webhook_signature_verifier,
)
from pramana.services.package_signing import HmacSignatureVerifier

_URL = "/webhooks/mentible/progress"
_SECRET = "webhook-secret"
_HDR = "X-Mentible-Signature"


def _sign(raw: bytes) -> str:
    return hmac.new(_SECRET.encode("utf-8"), raw, sha256).hexdigest()


def _raw(**payload) -> bytes:
    body = {"request_id": str(uuid.uuid4()), "tenant_id": str(uuid.uuid4()), "event": "progress"}
    body.update(payload)
    return json.dumps(body).encode("utf-8")


class FakeHandler:
    def __init__(self, *, applied: bool = True, status: str | None = "generating") -> None:
        self.applied = applied
        self.status = status
        self.calls: list = []

    async def handle(self, payload):
        self.calls.append(payload)
        return (self.applied, self.status)


def client(handler: FakeHandler) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_webhook_signature_verifier] = lambda: HmacSignatureVerifier(
        _SECRET
    )
    app.dependency_overrides[get_mentible_webhook_handler] = lambda: handler
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _post(c: TestClient, raw: bytes, *, signature: str | None) -> object:
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers[_HDR] = signature
    return c.post(_URL, content=raw, headers=headers)


def test_progress_event_applies_200() -> None:
    handler = FakeHandler(applied=True, status="generating")
    c = next(client(handler))
    raw = _raw(event="progress", progress_pct=42)
    resp = _post(c, raw, signature=_sign(raw))
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is True
    assert body["status"] == "generating"
    assert handler.calls and handler.calls[0].progress_pct == 42


def test_failure_event_applies() -> None:
    handler = FakeHandler(applied=True, status="failed")
    c = next(client(handler))
    raw = _raw(event="failure", detail="engine crashed")
    resp = _post(c, raw, signature=_sign(raw))
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    assert handler.calls[0].event == "failure"


def test_bad_signature_is_401() -> None:
    handler = FakeHandler()
    c = next(client(handler))
    raw = _raw()
    resp = _post(c, raw, signature="deadbeef")
    assert resp.status_code == 401
    assert handler.calls == []  # never reached the handler


def test_missing_signature_is_401() -> None:
    handler = FakeHandler()
    c = next(client(handler))
    raw = _raw()
    resp = _post(c, raw, signature=None)
    assert resp.status_code == 401
    assert handler.calls == []


def test_tampered_body_fails_signature() -> None:
    handler = FakeHandler()
    c = next(client(handler))
    raw = _raw(progress_pct=10)
    sig = _sign(raw)
    tampered = _raw(progress_pct=99)  # different bytes, old signature
    resp = _post(c, tampered, signature=sig)
    assert resp.status_code == 401


def test_noop_returns_200_applied_false() -> None:
    handler = FakeHandler(applied=False, status=None)
    c = next(client(handler))
    raw = _raw()
    resp = _post(c, raw, signature=_sign(raw))
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is False
    assert body["status"] is None


def test_malformed_body_after_valid_signature_is_422() -> None:
    handler = FakeHandler()
    c = next(client(handler))
    raw = json.dumps(
        {"tenant_id": str(uuid.uuid4()), "event": "progress"}
    ).encode()  # no request_id
    resp = _post(c, raw, signature=_sign(raw))
    assert resp.status_code == 422
    assert handler.calls == []


def test_out_of_range_pct_is_422() -> None:
    handler = FakeHandler()
    c = next(client(handler))
    raw = _raw(progress_pct=150)
    resp = _post(c, raw, signature=_sign(raw))
    assert resp.status_code == 422


def test_unknown_event_is_422() -> None:
    handler = FakeHandler()
    c = next(client(handler))
    raw = _raw(event="cancelled")
    resp = _post(c, raw, signature=_sign(raw))
    assert resp.status_code == 422
