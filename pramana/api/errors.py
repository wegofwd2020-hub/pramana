"""Map the Pramana exception hierarchy to HTTP responses.

The hierarchy (:mod:`pramana.exceptions`) is designed so the API layer can pick
a status code from the *class*, never by sniffing messages. Registered once on
the app via :func:`register_exception_handlers`.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from pramana.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DomainError,
    ExternalServiceError,
    NotFoundError,
    PramanaError,
    ValidationError,
)

# Most specific first — the handler walks this in order.
_STATUS_BY_TYPE: tuple[tuple[type[PramanaError], int], ...] = (
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED),
    (AuthorizationError, status.HTTP_403_FORBIDDEN),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    # ValidationError covers PackageValidationError + PackageIntegrityError
    # (a quarantined package is a 422 — the bytes were rejected at the boundary).
    # starlette renamed the 422 constant (…ENTITY → …CONTENT, RFC 9110); use the
    # current name when present, fall back to the literal so we don't pin a name.
    (ValidationError, getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)),
    (DomainError, status.HTTP_409_CONFLICT),
    (ExternalServiceError, status.HTTP_502_BAD_GATEWAY),
)


def _status_for(exc: PramanaError) -> int:
    for exc_type, code in _STATUS_BY_TYPE:
        if isinstance(exc, exc_type):
            return code
    return status.HTTP_400_BAD_REQUEST


def register_exception_handlers(app: FastAPI) -> None:
    """Install the single handler that renders any :class:`PramanaError`."""

    async def handle_pramana_error(_request: Request, exc: PramanaError) -> JSONResponse:
        body: dict[str, Any] = {
            "code": exc.code,
            "message": exc.message,
            "context": exc.context,
        }
        # Present only when detail was withheld, so a caller who has one knows
        # there is more to ask about and a caller who does not is not sent
        # looking for a log line that says nothing.
        if exc.incident_id is not None:
            body["incident_id"] = str(exc.incident_id)
        return JSONResponse(status_code=_status_for(exc), content={"error": body})

    # FastAPI dispatches on the exception class and its subclasses.
    app.add_exception_handler(PramanaError, handle_pramana_error)  # type: ignore[arg-type]
