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
NGINX = ROOT / "deploy" / "nginx" / "pramana.conf"
DEPLOY_COMPOSE = ROOT / "compose.deploy.yaml"
DEPLOY_SH = ROOT / "scripts" / "launch" / "deploy.sh"
SMOKE_SH = ROOT / "scripts" / "launch" / "smoke.sh"
DEPLOY_WF = ROOT / ".github" / "workflows" / "deploy-pramana.yml"


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


class TestNginxPathMount:
    """The host nginx block is versioned here, not left to live only on the box.

    Host nginx and its TLS certs sit outside compose and outside git; an
    unversioned manual edit caused a July outage, and this plan adds a second —
    compliance — app behind the same nginx. The block is codified so a review can
    see it and a deploy can copy it.

    Each assertion guards a silent failure:

    * Wrong ``proxy_pass`` form and the path prefix is not stripped, so every
      request 404s under ``/pramana``.
    * Miss the real client address and every attestation records nginx's own IP —
      a valid IP in the SOX audit chain identifying nobody. uvicorn already trusts
      this hop (``--proxy-headers``); nginx has to supply the truth.
    * Proxy anywhere but loopback and the container's ``127.0.0.1`` binding is
      unreachable.
    """

    def test_the_config_exists(self) -> None:
        assert NGINX.is_file(), (
            "deploy/nginx/pramana.conf is missing; the host nginx block must be "
            "versioned, not left to live only on the box"
        )

    def test_it_mounts_the_pramana_prefix(self) -> None:
        assert re.search(r"location\s+/pramana/?\s*\{", NGINX.read_text(encoding="utf-8"))

    def test_proxy_pass_strips_the_prefix(self) -> None:
        """A trailing slash on the upstream URL is what drops ``/pramana``."""
        text = NGINX.read_text(encoding="utf-8")
        assert re.search(r"proxy_pass\s+http://127\.0\.0\.1:8000/\s*;", text), (
            "proxy_pass must target 127.0.0.1:8000 with a trailing slash so the "
            "/pramana prefix is stripped before it reaches the app"
        )

    def test_it_forwards_the_real_client_ip(self) -> None:
        """Cloudflare's edge is the socket peer; CF-Connecting-IP carries the truth."""
        text = NGINX.read_text(encoding="utf-8")
        assert "CF-Connecting-IP" in text
        assert re.search(r"proxy_set_header\s+X-Forwarded-For", text)


class TestProdCompose:
    """``compose.deploy.yaml`` is the production stack; ``compose.yaml`` is dev.

    The dev compose inlines throwaway secrets and runs ENVIRONMENT=development —
    shipping it would publish /docs, trust a fake SECRET_KEY, and (worst) it
    reads nothing from a secrets file. These assert the production compose is
    genuinely production-shaped, because a deploy that quietly used the dev one
    would look healthy while being wrong.
    """

    def test_the_api_port_binds_loopback_only(self) -> None:
        """Same rule as dev, and it matters more here: host nginx is sole ingress."""
        text = DEPLOY_COMPOSE.read_text("utf-8")
        published = re.findall(r'^\s*-\s*"([^"]*:8000)"', text, re.MULTILINE)
        assert published, "no published mapping for the API port found"
        for mapping in published:
            assert mapping.startswith("127.0.0.1:"), (
                f"API published as {mapping!r}; that exposes it on the box's public IP"
            )

    def test_it_runs_in_the_production_environment(self) -> None:
        """Development leaves /docs and the OpenAPI schema publicly served."""
        assert re.search(r"ENVIRONMENT:\s*production", DEPLOY_COMPOSE.read_text("utf-8"))

    def test_secrets_come_from_an_env_file_not_inlined(self) -> None:
        """A real SECRET_KEY / DB password must not live in a committed compose."""
        text = DEPLOY_COMPOSE.read_text("utf-8")
        assert "env_file" in text, "production compose must read secrets from a .env file"
        assert "local-development-only-not-a-real-secret" not in text, (
            "the dev throwaway SECRET_KEY leaked into the production compose"
        )

    def test_the_database_has_a_persistent_volume(self) -> None:
        """Compliance evidence has a 7-year retention floor; data cannot be ephemeral."""
        assert "/var/lib/postgresql/data" in DEPLOY_COMPOSE.read_text("utf-8")

    def test_the_public_base_url_is_wired(self) -> None:
        """Without it certificates print a relative verify link and root_path is empty."""
        assert "PUBLIC_BASE_URL" in DEPLOY_COMPOSE.read_text("utf-8")


class TestDatabasePasswordIsNotUrlEmbedded:
    """The DB password must never be interpolated into the DSN.

    A password with a URL-special char (``@ : / # ? % =``) corrupts
    ``postgresql+asyncpg://pramana:<pw>@postgres`` — asyncpg then parses the
    wrong host/password and authentication fails. This bit a real Day-0 deploy
    (base64 password). asyncpg honours the libpq ``PGPASSWORD`` env var when the
    DSN omits the password, so it travels as a plain literal — like Postgres's
    own ``POSTGRES_PASSWORD`` — and is never URL-parsed.
    """

    def _database_url_lines(self) -> list[str]:
        return [
            line
            for line in DEPLOY_COMPOSE.read_text("utf-8").splitlines()
            if "DATABASE_URL" in line
        ]

    def test_the_password_is_not_interpolated_into_the_dsn(self) -> None:
        lines = self._database_url_lines()
        assert lines, "no DATABASE_URL found in the production compose"
        for line in lines:
            assert "POSTGRES_PASSWORD" not in line, (
                "the DB password is interpolated into DATABASE_URL; a URL-special "
                "character corrupts the DSN. Omit the password from the URL and "
                "pass it via PGPASSWORD instead."
            )
            # Belt-and-braces: the userinfo must carry no password (`user:pw@`).
            assert "pramana:" not in line, "DATABASE_URL still embeds a password"

    def test_the_password_travels_via_pgpassword(self) -> None:
        assert "PGPASSWORD" in DEPLOY_COMPOSE.read_text("utf-8")


class TestDeployScripts:
    def test_deploy_and_smoke_scripts_exist(self) -> None:
        assert DEPLOY_SH.is_file(), "scripts/launch/deploy.sh is missing"
        assert SMOKE_SH.is_file(), "scripts/launch/smoke.sh is missing"

    def test_deploy_uses_the_production_compose_and_an_env_file(self) -> None:
        text = DEPLOY_SH.read_text("utf-8")
        assert "compose.deploy.yaml" in text
        assert "--env-file" in text

    def test_smoke_asserts_on_the_body_not_only_the_status(self) -> None:
        """A stray service on :8000 once answered a health probe convincingly —
        the check must look at the payload, not just a 200."""
        assert '"status"' in SMOKE_SH.read_text("utf-8") or "status" in SMOKE_SH.read_text("utf-8")


class TestDeployWorkflow:
    def test_the_workflow_exists(self) -> None:
        assert DEPLOY_WF.is_file(), ".github/workflows/deploy-pramana.yml is missing"

    def test_it_is_gated_until_the_box_exists(self) -> None:
        """Auto-deploy must stay dormant until the VPS + secrets are in place."""
        assert "PRAMANA_DEPLOY_ENABLED" in DEPLOY_WF.read_text("utf-8")

    def test_smoke_retries_to_a_deadline(self) -> None:
        """A fresh route is not live until the rebuild finishes; assert-on-first
        turns propagation lag into a false incident."""
        assert "deadline" in DEPLOY_WF.read_text("utf-8")

    def test_it_files_an_incident_on_real_failure(self) -> None:
        assert "incident:pramana" in DEPLOY_WF.read_text("utf-8")

    def test_smoke_targets_the_path_mount(self) -> None:
        assert "mambakkam.net/pramana" in DEPLOY_WF.read_text("utf-8")


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


class TestImageShipsOperationalScripts:
    """The runtime image must contain ``scripts/``.

    A fresh deployment is bootstrapped by scripts that run *inside* the api
    container — ``seed_user.py``/``grant_role.py`` to make the first admin,
    ``archive_audit.py`` for WORM export. If the Dockerfile copies only the
    package and alembic, ``docker compose run api python scripts/…`` fails with
    "No such file or directory", which is exactly how the first admin seed broke
    on the box.
    """

    def test_scripts_are_copied_into_the_runtime_stage(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        assert re.search(r"COPY[^\n]*\bscripts/\s+scripts/", text), (
            "the Dockerfile does not copy scripts/ into the image, so the "
            "bootstrap scripts cannot run inside the api container"
        )
