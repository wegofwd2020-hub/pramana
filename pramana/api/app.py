"""FastAPI application factory.

The first HTTP surface in Pramana: the ``consumer_library`` ingestion endpoint
(Mentible ADR-011). Kept as a factory so tests build an isolated app and
override dependencies without touching module-global state.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pramana.api import (
    assignments,
    audit,
    certificates,
    consumer,
    consumer_admin,
    consumer_library,
    content_drafts,
    content_requests,
    exports,
    frameworks,
    roles,
    webhooks,
)
from pramana.api.dependencies import get_db_session
from pramana.api.errors import register_exception_handlers
from pramana.config import Settings, get_settings

logger = structlog.get_logger(__name__)

#: Upper bound on the readiness query. Shorter than any sensible probe timeout,
#: so the endpoint answers 503 rather than leaving the prober to time out.
READINESS_TIMEOUT_SECONDS = 2.0


def create_app(*, settings: Settings | None = None) -> FastAPI:
    """Construct and configure the Pramana API application.

    ``settings`` is injectable so tests can build an app for a specific
    environment without mutating process state.
    """
    settings = settings or get_settings()

    # The interactive docs publish every route, parameter and schema of a
    # compliance product to anyone who finds the hostname. Serving openapi.json
    # while hiding the UI would be theatre, so all three go together.
    docs_enabled = not settings.is_production

    app = FastAPI(
        title="Pramana",
        description="Compliance training delivery + tracking.",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    register_exception_handlers(app)
    app.include_router(consumer.router)
    app.include_router(consumer_admin.router)
    app.include_router(consumer_library.router)
    app.include_router(content_drafts.router)
    app.include_router(content_requests.router)
    app.include_router(frameworks.router)
    app.include_router(webhooks.router)
    app.include_router(assignments.router)
    app.include_router(certificates.router)
    app.include_router(audit.router)
    app.include_router(exports.router)
    app.include_router(roles.router)
    app.include_router(audit.evidence_router)

    @app.get("/health", tags=["meta"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        """Is the process up?

        Deliberately checks nothing else. An orchestrator restarts a container
        whose liveness probe fails, so making this depend on the database would
        turn a brief outage into a crash loop. *Readiness* is the probe that
        should notice a database problem — see ``/health/ready``.
        """
        return {"status": "ok"}

    @app.get("/health/ready", tags=["meta"], summary="Readiness probe")
    async def ready(
        session: Annotated[AsyncSession, Depends(get_db_session)],
        response: Response,
    ) -> dict[str, str]:
        """Can this instance actually serve a request?

        Every meaningful route needs the database, so readiness is a real query
        rather than a constant. Returns 503 when it fails, which tells an
        orchestrator to stop routing traffic here without restarting anything.

        Bounded by :data:`READINESS_TIMEOUT_SECONDS`. Without it the check
        *hangs* rather than failing when the database is stopped rather than
        refusing — the driver waits on its own much longer connect timeout. A
        probe that hangs is worse than one that fails: it occupies a worker and
        delays the very detection it exists to provide.

        The underlying error is logged, never returned: a probe response is
        widely readable and the exception text can carry the connection string.
        """
        try:
            await asyncio.wait_for(
                session.execute(text("SELECT 1")), timeout=READINESS_TIMEOUT_SECONDS
            )
        except Exception:
            logger.warning("readiness_probe_failed", exc_info=True)
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not ready", "database": "unavailable"}
        return {"status": "ready", "database": "ok"}

    return app
