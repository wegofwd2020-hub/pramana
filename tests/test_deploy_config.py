"""The deployment configuration says what it needs to say.

These assert on `compose.yaml`, the `Dockerfile` and the nginx server block as
text. That is unusual, and deliberate: the failures they guard are silent.

* Publishing the API on every interface puts it on the box's public IP, past
  Cloudflare and past TLS — and reachable from the other application sharing the
  host.
* `--forwarded-allow-ips=*` makes uvicorn trust `X-Forwarded-For` from any peer,
  so anyone who reaches the port forges their own attestation IP. Fabricated
  evidence is worse than absent evidence.
* Without `real_ip_header CF-Connecting-IP`, the address that survives to the
  audit log is Cloudflare's edge, not the learner's.

None of those raise anything. They just produce records that look fine.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yaml"
DOCKERFILE = ROOT / "Dockerfile"
NGINX = ROOT / "deploy" / "nginx" / "pramana.mambakkam.net.conf"


class TestComposeExposure:
    def test_the_api_port_binds_loopback_only(self) -> None:
        """Host nginx is the only ingress; the container must not be public."""
        text = COMPOSE.read_text(encoding="utf-8")
        published = re.findall(r'^\s*-\s*"([^"]*:8000)"', text, re.MULTILINE)
        assert published, "no published mapping for the API port found"
        for mapping in published:
            assert mapping.startswith("127.0.0.1:"), (
                f"API published as {mapping!r}; on a shared host that exposes it "
                f"on the public IP, bypassing Cloudflare and TLS"
            )


class TestUvicornProxyTrust:
    def test_proxy_headers_are_enabled(self) -> None:
        """Otherwise X-Forwarded-For is ignored and the attestation IP is the gateway."""
        assert "--proxy-headers" in DOCKERFILE.read_text(encoding="utf-8")

    def test_forwarded_ips_are_not_trusted_from_everywhere(self) -> None:
        """`*` would let any caller forge the IP recorded as SOX evidence."""
        text = DOCKERFILE.read_text(encoding="utf-8")
        assert '--forwarded-allow-ips", "*"' not in text
        assert "--forwarded-allow-ips=*" not in text

    def test_a_trusted_proxy_is_configured(self) -> None:
        assert "--forwarded-allow-ips" in DOCKERFILE.read_text(encoding="utf-8")


@pytest.mark.skipif(not NGINX.exists(), reason="nginx server block not present")
class TestNginxServerBlock:
    def _text(self) -> str:
        return NGINX.read_text(encoding="utf-8")

    def test_restores_the_real_client_ip_from_cloudflare(self) -> None:
        """Without this the audit log records Cloudflare's edge as the learner."""
        text = self._text()
        assert "real_ip_header CF-Connecting-IP" in text
        assert "set_real_ip_from" in text

    def test_forwards_the_client_ip_onward(self) -> None:
        assert "X-Forwarded-For" in self._text()

    def test_forwards_the_original_scheme_and_host(self) -> None:
        text = self._text()
        assert "X-Forwarded-Proto" in text
        assert "proxy_set_header Host" in text

    def test_proxies_to_loopback(self) -> None:
        """Matching the compose binding; anything else would not reach the app."""
        assert re.search(r"proxy_pass\s+http://127\.0\.0\.1:", self._text())

    def test_the_docs_are_blocked_at_the_edge(self) -> None:
        """Defence in depth: the app disables them outside development, nginx too.

        Asserts the location block actually *refuses* rather than merely
        mentioning the path — a block that proxied /docs would still match a
        looser pattern.
        """
        text = self._text()
        block = re.search(r"location[^\n{]*docs[^{]*\{(?P<body>[^}]*)\}", text, re.IGNORECASE)
        assert block, "no location block covering /docs"
        assert "return 404" in block.group("body"), (
            "the /docs location exists but does not refuse the request"
        )
