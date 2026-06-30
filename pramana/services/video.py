"""Composition root for the in-process video provider (ADR-026).

Builds a ``wegofwd_video.VideoProvider`` from settings — the **managed** key
regime, exactly like :mod:`pramana.services.llm`: Pramana holds the key and passes
it to the seam per call (the seam never sources or logs keys, ADR-026 D2). Kept
tiny and separate so the generation service and API layer depend on the
``VideoProvider`` interface, and tests inject a fake one.

Empty ``video_api_key`` in dev/test → ``build_provider`` raises, so callers wire a
fake provider in tests (the default; live Veo is gated on the first real
integration, ADR-026 D7).
"""

from __future__ import annotations

from wegofwd_video import VideoProvider, build_provider

from pramana.config import Settings


def build_video_provider(settings: Settings) -> VideoProvider:
    """Construct the managed in-process video provider from settings.

    Raises:
        wegofwd_video.VideoConfigurationError: Unknown provider, or empty key for a
            BYOK provider such as ``veo``.
    """
    return build_provider(
        settings.video_provider,
        api_key=settings.video_api_key.get_secret_value(),
        model=settings.video_model,
    )
