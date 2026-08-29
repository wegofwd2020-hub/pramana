"""Tests for :mod:`pramana.config`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pramana.config import Environment, LogLevel, Settings, get_settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
_ASSIGNMENT_RE = re.compile(r"^([A-Z0-9_]+)=", re.MULTILINE)


def _documented_names() -> set[str]:
    """Every ``NAME=`` key declared in ``.env.example``."""
    return set(_ASSIGNMENT_RE.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))


def _setting_names() -> set[str]:
    """Every environment variable :class:`Settings` reads."""
    return {name.upper() for name in Settings.model_fields}


class TestSettings:
    """Settings parsing and validation."""

    def test_loads_from_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings are loaded from environment variables."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        monkeypatch.setenv("SECRET_KEY", "super-secret")
        get_settings.cache_clear()

        settings = get_settings()

        assert settings.environment is Environment.PRODUCTION
        assert settings.log_level is LogLevel.WARNING
        assert settings.secret_key.get_secret_value() == "super-secret"

    def test_is_production_helper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`is_production` returns True only for production environment."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("SECRET_KEY", "x")
        get_settings.cache_clear()
        assert get_settings().is_production is True

        monkeypatch.setenv("ENVIRONMENT", "staging")
        get_settings.cache_clear()
        assert get_settings().is_production is False

    def test_compliance_defaults(self, settings: Settings) -> None:
        """Compliance defaults match Section 8 of the resolved decisions doc."""
        assert settings.default_pass_threshold_pct == 80
        assert settings.default_cooldown_days == 365
        assert settings.default_max_attempts == 2
        assert settings.default_record_retention_years == 7

    def test_pass_threshold_rejects_out_of_range(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Values outside 0..100 are rejected at parse time."""
        monkeypatch.setenv("DEFAULT_PASS_THRESHOLD_PCT", "150")
        monkeypatch.setenv("SECRET_KEY", "x")
        get_settings.cache_clear()
        with pytest.raises(Exception):  # pydantic.ValidationError
            get_settings()

    def test_settings_singleton_is_cached(self, settings: Settings) -> None:
        """``get_settings`` returns the same instance on repeated calls."""
        assert get_settings() is settings


class TestEnvExampleIsComplete:
    """``.env.example`` is the deployer's onboarding contract — keep it honest.

    Nothing else validates that file, so it rots silently: three subsystems
    (Mentible handoff, LLM drafting, video generation) shipped without their
    settings ever being added, leaving 14 of 44 undocumented. A deployer
    following it left both HMAC secrets empty and got a broken ingest with no
    hint as to why.

    These tests are cheap and they fail loudly the moment a new setting is added
    without documenting it.
    """

    def test_every_setting_is_documented(self) -> None:
        """A new field on ``Settings`` must be added to ``.env.example``."""
        missing = _setting_names() - _documented_names()
        assert not missing, (
            f".env.example does not document {len(missing)} setting(s): "
            f"{', '.join(sorted(missing))}. Add them so a deployer copying the "
            f"file gets a working configuration."
        )

    def test_no_stale_entries(self) -> None:
        """``.env.example`` must not list variables that are no longer settings."""
        stale = _documented_names() - _setting_names()
        assert not stale, (
            f".env.example lists {len(stale)} variable(s) that Settings no longer "
            f"reads: {', '.join(sorted(stale))}. Setting them would do nothing, so "
            f"remove them."
        )

    def test_example_file_loads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The committed example parses into valid Settings.

        Documenting a name is not enough — the *value* beside it has to be one
        pydantic accepts, or the file is a trap rather than a template. Env vars
        are cleared first so the file is genuinely the source.
        """
        for name in _setting_names():
            monkeypatch.delenv(name, raising=False)

        settings = Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]

        assert settings.environment is Environment.DEVELOPMENT
        assert settings.default_pass_threshold_pct == 80
        # Secrets ship empty on purpose; ingestion refuses an empty key rather
        # than accepting unsigned packages, so this fails closed.
        assert settings.mentible_package_hmac_secret.get_secret_value() == ""
