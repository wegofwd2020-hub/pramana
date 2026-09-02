"""The deployment configuration says what it needs to say.

These assert on `compose.yaml`, the `Dockerfile` and the nginx server block as
text. That is unusual, and deliberate: the failures they guard are silent.

* Publishing the API on every interface puts it on the box's public IP, past
  Cloudflare and past TLS — and reachable from the other application sharing the
  host.
* `--forwarded-allow-ips=*` makes uvicorn trust `X-Forwarded-For` from any peer,
  so anyone who reaches the port forges their own attestation IP. Fabricated
  evidence is worse than absent evidence.
* Behind Cloudflare the socket peer is Cloudflare's edge, so nginx must also
  restore the real address — tracked with the hosting work, not asserted here.

None of those raise anything. They just produce records that look fine.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yaml"
DOCKERFILE = ROOT / "Dockerfile"


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
