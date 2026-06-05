"""Pydantic request/response schemas for the HTTP API."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestPackageRequest(BaseModel):
    """Body of a consumable-package push (Mentible ADR-011 §6).

    ``tenant_id`` and ``course_id`` say *where* the package lands in Pramana
    (Mentible does not know Pramana's ids — they are supplied by the operator /
    drop configuration). ``manifest`` is the raw ADR-011 manifest, validated and
    integrity-checked downstream in the domain.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: uuid.UUID
    course_id: uuid.UUID
    manifest: dict[str, Any] = Field(
        description="The full Consumable Package manifest (ADR-011 §4)."
    )


class IngestPackageResponse(BaseModel):
    """Result of a successful ingestion: an untrusted ``RECEIVED`` draft."""

    draft_id: uuid.UUID
    status: str
    package_id: uuid.UUID
    package_version: int
