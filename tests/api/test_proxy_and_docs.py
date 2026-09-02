"""Behaviour that only shows up behind a reverse proxy.

Two things break quietly when this application moves behind nginx, and neither
raises an error:

* **The attestation IP becomes the proxy's.** ``attestation_ip`` is SOX evidence
  — the resolved decisions doc has the completion attestation capturing
  timestamp, IP, browser fingerprint and attestation text version. Read from the
  socket peer, every attestation in production records the same internal gateway
  address: a valid IP, in a valid column, in the audit chain, identifying nobody.
* **``/docs`` publishes the full API surface** of a compliance product to anyone
  who finds the hostname.

Both are configuration rather than logic, which is exactly why they need tests —
nothing else would notice.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pramana.api.app import create_app
from pramana.config import Environment, Settings, get_settings


def _client(**settings_overrides: object) -> TestClient:
    if settings_overrides:
        base = {"secret_key": "x", **settings_overrides}
        get_settings.cache_clear()
        app = create_app(settings=Settings(**base))  # type: ignore[arg-type]
    else:
        app = create_app()
    return TestClient(app)


class TestApiDocsExposure:
    def test_docs_are_available_in_development(self) -> None:
        """Local work needs them; this is only about production."""
        assert _client(environment=Environment.DEVELOPMENT).get("/docs").status_code == 200

    def test_docs_are_disabled_in_production(self) -> None:
        """A compliance product should not publish its whole surface to the world."""
        client = _client(environment=Environment.PRODUCTION)
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404

    def test_the_openapi_schema_is_disabled_in_production_too(self) -> None:
        """Hiding the UI while serving openapi.json would be theatre."""
        assert _client(environment=Environment.PRODUCTION).get("/openapi.json").status_code == 404

    def test_health_probes_survive_docs_being_disabled(self) -> None:
        """An orchestrator still needs these in production."""
        assert _client(environment=Environment.PRODUCTION).get("/health").status_code == 200


class TestForwardedClientIp:
    """`--proxy-headers` is what makes these pass in a real deployment.

    Starlette's TestClient does not run uvicorn's ProxyHeaders middleware, so
    these assert the *application-level* helper: given a request whose scope
    carries a forwarded peer, the recorded address is that one rather than the
    socket peer. The deployment half — `--proxy-headers` plus a scoped
    `--forwarded-allow-ips` — is asserted in tests/test_deploy_config.py.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("203.0.113.9", "203.0.113.9"),
            ("2001:db8::1", "2001:db8::1"),
            ("not-an-ip", None),
            ("", None),
        ],
    )
    def test_only_real_addresses_are_recorded(self, raw: str, expected: str | None) -> None:
        """The INET column rejects hostnames, so a non-address must become NULL."""
        from pramana.api.assignments import _client_ip

        class _Req:
            client = type("C", (), {"host": raw})()

        assert _client_ip(_Req()) == expected  # type: ignore[arg-type]

    def test_a_missing_peer_is_not_an_error(self) -> None:
        from pramana.api.assignments import _client_ip

        class _Req:
            client = None

        assert _client_ip(_Req()) is None  # type: ignore[arg-type]
