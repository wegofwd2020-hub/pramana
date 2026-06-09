"""Test helpers for building Mentible Consumable Package manifests.

Mints manifests whose ``content_hash`` and ``signature`` are *correct* for the
domain's canonicalization, so verification passes — then individual tests
mutate a field to exercise the failure paths.
"""

from __future__ import annotations

import uuid
from typing import Any

from pramana.domain.consumable_package import canonical_json, compute_content_hash
from pramana.services.package_signing import HmacSignatureVerifier

DEFAULT_SECRET = "test-mentible-hmac-secret"


def make_manifest(**overrides: Any) -> dict[str, Any]:
    """Return a structurally valid manifest (content/signature filled in by
    :func:`sign_manifest` — call that to make it verifiable)."""
    manifest: dict[str, Any] = {
        "package_id": str(uuid.uuid4()),
        "package_version": 1,
        "title": "SOX §404 Controls for Managers",
        "frameworks": ["sox"],
        "source_definitions": [
            {
                "framework": "sox",
                "clause": "404",
                "ref": "pramana/docs/frameworks/framework_sox.md#404",
            }
        ],
        "provenance": {
            "engine": "mentible",
            "model": "claude-sonnet-4-6",
            "provider": "anthropic",
            "prompt_version": "psai-2026-06",
            "generated_at": "2026-06-05T12:00:00Z",
        },
        "modules": [
            {
                "order": 0,
                "heading": "What §404 requires",
                "body_markdown": "Management must assess internal controls...",
                "citations": [{"framework": "sox", "clause": "404"}],
            }
        ],
        "quiz": {
            "pass_threshold_pct": 80,
            "questions": [
                {
                    "prompt": "Who attests to internal controls under §404?",
                    "options": ["Management", "Auditors", "The SEC"],
                    "answer_index": 0,
                }
            ],
        },
        "assets": [{"id": "fig-1", "type": "animated_svg", "uri": "assets/fig-1.svg"}],
        "artifacts": [{"format": "epub3", "uri": "artifact.epub"}],
    }
    manifest.update(overrides)
    return manifest


def sign_manifest(manifest: dict[str, Any], *, secret: str = DEFAULT_SECRET) -> dict[str, Any]:
    """Fill in a correct ``content_hash`` then a correct ``signature``.

    Mutates and returns ``manifest``. Order matters: the signature covers the
    content_hash, exactly as the domain verifies it.
    """
    manifest["content_hash"] = compute_content_hash(
        canonical_json({"modules": manifest["modules"], "quiz": manifest["quiz"]})
    )
    signing_payload = canonical_json({k: v for k, v in manifest.items() if k != "signature"})
    manifest["signature"] = HmacSignatureVerifier(secret).sign(signing_payload)
    return manifest


def make_signed_manifest(*, secret: str = DEFAULT_SECRET, **overrides: Any) -> dict[str, Any]:
    """Convenience: a fully valid, verifiable manifest."""
    return sign_manifest(make_manifest(**overrides), secret=secret)
