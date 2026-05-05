"""Tests for :mod:`pramana.config`."""

from __future__ import annotations

import pytest

from pramana.config import Environment, LogLevel, Settings, get_settings


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

    def test_pass_threshold_rejects_out_of_range(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Values outside 0..100 are rejected at parse time."""
        monkeypatch.setenv("DEFAULT_PASS_THRESHOLD_PCT", "150")
        monkeypatch.setenv("SECRET_KEY", "x")
        get_settings.cache_clear()
        with pytest.raises(Exception):  # pydantic.ValidationError
            get_settings()

    def test_settings_singleton_is_cached(self, settings: Settings) -> None:
        """``get_settings`` returns the same instance on repeated calls."""
        assert get_settings() is settings
