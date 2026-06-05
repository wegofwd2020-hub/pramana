"""FastAPI application factory.

The first HTTP surface in Pramana: the ``consumer_library`` ingestion endpoint
(Mentible ADR-011). Kept as a factory so tests build an isolated app and
override dependencies without touching module-global state.
"""

from __future__ import annotations

from fastapi import FastAPI

from pramana.api import consumer_library, content_drafts
from pramana.api.errors import register_exception_handlers


def create_app() -> FastAPI:
    """Construct and configure the Pramana API application."""
    app = FastAPI(
        title="Pramana",
        description="Compliance training delivery + tracking.",
        version="0.1.0",
    )

    register_exception_handlers(app)
    app.include_router(consumer_library.router)
    app.include_router(content_drafts.router)

    @app.get("/health", tags=["meta"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
