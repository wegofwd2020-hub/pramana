"""Composition root for the in-process LLM provider (ADR-013).

Builds a ``wegofwd_llm.Provider`` from settings — the **managed** key regime:
Pramana holds the key and passes it to the seam per call (the seam never sources
or logs keys, ADR-012 D3). Kept tiny and separate so the generation service and
the API layer depend on the ``Provider`` interface, and tests inject a fake one.
"""

from __future__ import annotations

from wegofwd_llm import Provider, build_provider

from pramana.config import Settings


def build_llm_provider(settings: Settings) -> Provider:
    """Construct the managed in-process provider from settings.

    Raises:
        wegofwd_llm.LLMConfigurationError: Unknown provider, or empty key.
    """
    return build_provider(
        settings.llm_provider,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
    )
