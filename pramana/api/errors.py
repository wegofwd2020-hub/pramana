"""Map the Pramana exception hierarchy to HTTP responses.

The hierarchy (:mod:`pramana.exceptions`) is designed so the API layer can pick
a status code from the *class*, never by sniffing messages. Registered once on
the app via :func:`register_exception_handlers`.
"""

from __future__ import annotations

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
    (ValidationError, status.HTTP_422_UNPROCESSABLE_ENTITY),
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
        return JSONResponse(
            status_code=_status_for(exc),
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "context": exc.context,
                }
            },
        )

    # FastAPI dispatches on the exception class and its subclasses.
    app.add_exception_handler(PramanaError, handle_pramana_error)  # type: ignore[arg-type]
