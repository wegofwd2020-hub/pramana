"""Secrets come from the environment and stay out of anything renderable.

PR-4 asks that secrets are sourced from a secret manager or the environment and
never appear in source. They are, and they do not — but nothing enforced it, so
the next setting added as a plain ``str`` would pass review on the strength of
the ones around it looking careful.

The rule these tests encode: a field whose *name* says it holds a credential
must be :class:`~pydantic.SecretStr`, so that rendering the settings object
cannot spill it, and ``SECRET_KEY`` must have no default, so no deployment can
run on a value that is also in the repository.
"""

from __future__ import annotations

import re

import pytest
from pydantic import SecretStr

from pramana.config import Settings

#: Names that look like credentials.
_SECRET_NAME = re.compile(r"secret|password|token|key|credential", re.IGNORECASE)

#: Name matches that are not credentials, and why. Anything added here is a
#: claim that the value is safe to print.
_NOT_ACTUALLY_SECRET: dict[str, str] = {
    "aws_access_key_id": (
        "an identifier, not a credential — the paired secret is "
        "aws_secret_access_key, which is a SecretStr"
    ),
    "llm_max_tokens": "an int; matches the pattern only on the word 'token'",
}


def _secret_named_fields() -> list[str]:
    return [name for name in Settings.model_fields if _SECRET_NAME.search(name)]


class TestSecretsAreTyped:
    def test_every_credential_field_is_a_secretstr(self) -> None:
        """A plain ``str`` credential is one log line away from disclosure."""
        plain = [
            name
            for name in _secret_named_fields()
            if name not in _NOT_ACTUALLY_SECRET
            and Settings.model_fields[name].annotation is not SecretStr
        ]
        assert not plain, (
            f"credential-shaped settings that are not SecretStr: {plain}. "
            "Either type them SecretStr or justify them in _NOT_ACTUALLY_SECRET."
        )

    def test_the_exclusion_list_has_no_stale_entries(self) -> None:
        """An excluded field that no longer exists silently weakens the check."""
        stale = sorted(set(_NOT_ACTUALLY_SECRET) - set(Settings.model_fields))
        assert not stale, f"_NOT_ACTUALLY_SECRET names fields that are gone: {stale}"

    def test_secret_key_has_no_default(self) -> None:
        """A default signing key in source is a key everybody has."""
        assert Settings.model_fields["secret_key"].is_required()


class TestSecretsDoNotSurviveRendering:
    """The property SecretStr actually buys: printing the object is safe."""

    @pytest.mark.parametrize(
        ("env_var", "value"),
        [
            ("SECRET_KEY", "signing-key-must-not-appear"),
            ("LLM_API_KEY", "sk-must-not-appear"),
            ("SMTP_PASSWORD", "smtp-must-not-appear"),
            ("MENTIBLE_WEBHOOK_HMAC_SECRET", "hmac-must-not-appear"),
        ],
    )
    def test_repr_does_not_contain_the_value(
        self, monkeypatch: pytest.MonkeyPatch, env_var: str, value: str
    ) -> None:
        monkeypatch.setenv(env_var, value)
        assert value not in repr(Settings())

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "KNOWN GAP, tracked in TICKETS/PR-4: database_url is a plain str, so "
            "its password survives repr() and model_dump(). Nothing renders "
            "settings today, and the one path that put the DSN into an HTTP "
            "response body is fixed (see tests/db/test_session_error_redaction.py), "
            "so this is latent rather than live. Typing it SecretStr means "
            "touching every consumer including alembic/env.py — a deliberate "
            "change, not a drive-by. When that lands, this test starts passing "
            "and strict=True will fail the run so the xfail gets removed."
        ),
    )
    def test_repr_does_not_contain_the_database_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "DATABASE_URL", "postgresql+asyncpg://pramana:dsn-must-not-appear@h:5432/d"
        )
        assert "dsn-must-not-appear" not in repr(Settings())


class TestNoSecretsInSource:
    """The literal reading of the criterion: nothing credential-shaped is committed."""

    def test_no_settings_default_carries_a_credential_value(self) -> None:
        """Empty defaults are fine; a populated one would ship a secret."""
        populated = []
        for name in _secret_named_fields():
            if name in _NOT_ACTUALLY_SECRET:
                continue
            default = Settings.model_fields[name].default
            if isinstance(default, SecretStr) and default.get_secret_value():
                populated.append(name)
        assert not populated, f"settings ship a non-empty credential default: {populated}"
