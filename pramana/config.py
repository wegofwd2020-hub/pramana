"""Application configuration.

Loads settings from environment variables (and `.env` file in development).
All settings are typed; misconfiguration fails fast at startup rather than at
first use.

Per the resolved decisions document, several values default to compliance
defaults (e.g. ``DEFAULT_PASS_THRESHOLD_PCT = 80``) but may be overridden
per-course at runtime.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Logging severity."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """Strongly typed application settings.

    Loaded from environment and (in development) `.env`.

    Attributes:
        environment: Deployment environment.
        log_level: Minimum log severity.
        secret_key: Symmetric key for signing transient tokens.
        database_url: SQLAlchemy async DSN.
        redis_url: Redis connection string.
        celery_broker_url: Celery broker URL (defaults to Redis DB 1).
        celery_result_backend: Celery result backend URL.
        sso_issuer_url: OIDC issuer URL (used for JWT verification).
        sso_client_id: OIDC client ID.
        sso_client_secret: OIDC client secret.
        jwt_algorithm: JWT signing algorithm (asymmetric, e.g. RS256).
        jwt_audience: Expected JWT audience claim.
        s3_bucket_video: Video asset bucket.
        s3_bucket_certificates: PDF certificate bucket.
        s3_bucket_audit_archive: Append-only audit-log archive bucket
            (Object Lock recommended in production).
        aws_region: AWS region for S3 access.
        smtp_host: Outbound SMTP host.
        smtp_port: Outbound SMTP port.
        smtp_from_address: Default `From:` for outbound mail.
        default_pass_threshold_pct: Default pass threshold for new courses
            (overridable per course).
        default_cooldown_days: Default re-assignment cooldown.
        default_max_attempts: Maximum attempts per assignment.
        default_record_retention_years: Minimum retention for compliance
            evidence (SOX-driven default of 7 years).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    environment: Environment = Environment.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO
    secret_key: SecretStr

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://pramana:pramana@localhost:5432/pramana"
    )
    database_pool_size: Annotated[int, Field(ge=1, le=100)] = 10
    database_max_overflow: Annotated[int, Field(ge=0, le=200)] = 20
    database_echo: bool = False

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Auth (OIDC / SSO)
    sso_issuer_url: str = ""
    sso_client_id: str = ""
    sso_client_secret: SecretStr = SecretStr("")
    jwt_algorithm: str = "RS256"
    jwt_audience: str = "pramana"

    # Object storage
    s3_bucket_video: str = "pramana-video-dev"
    s3_bucket_certificates: str = "pramana-certs-dev"
    s3_bucket_audit_archive: str = "pramana-audit-dev"
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: SecretStr = SecretStr("")

    # Email
    smtp_host: str = "localhost"
    smtp_port: Annotated[int, Field(ge=1, le=65535)] = 1025
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_address: str = "noreply@pramana.example.com"

    # Compliance defaults
    default_pass_threshold_pct: Annotated[int, Field(ge=0, le=100)] = 80
    default_cooldown_days: Annotated[int, Field(ge=0, le=3650)] = 365
    default_max_attempts: Annotated[int, Field(ge=1, le=10)] = 2
    default_record_retention_years: Annotated[int, Field(ge=1, le=20)] = 7

    @property
    def is_production(self) -> bool:
        """Return True if running in production."""
        return self.environment == Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton application settings.

    Cached so settings are read from the environment exactly once per process.
    Tests that need to override settings should call ``get_settings.cache_clear()``
    after mutating environment variables.

    Returns:
        The parsed and validated :class:`Settings` instance.

    Raises:
        pydantic.ValidationError: If required settings are missing or malformed.
    """
    return Settings()  # type: ignore[call-arg]
