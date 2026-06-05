"""Pramana exception hierarchy.

All application errors derive from :class:`PramanaError`. The hierarchy is
designed so that the API layer can map exception classes to HTTP status codes
without inspecting messages or codes ad-hoc.

Hierarchy::

    PramanaError                            # base; never raised directly
    ├── DomainError                         # business-rule violations
    │   ├── InvalidStateTransitionError     # state machine rejection
    │   ├── CooldownActiveError             # course re-assignment blocked
    │   ├── MaxAttemptsExceededError        # cannot retry
    │   ├── ConcurrentAssignmentError       # FR7 violation
    │   └── SeparationOfDutiesError         # SOX role conflict
    ├── NotFoundError                       # entity does not exist
    ├── ConflictError                       # uniqueness / optimistic-lock conflict
    │   └── DuplicatePackageError           # (package_id, version) already ingested
    ├── ValidationError                     # input validation failure
    │   ├── PackageValidationError          # consumable-package manifest malformed
    │   └── PackageIntegrityError           # signature / content_hash mismatch (quarantine)
    ├── AuthenticationError                 # missing/invalid credentials
    ├── AuthorizationError                  # authenticated but forbidden
    └── ExternalServiceError                # downstream system failure
        ├── DatabaseError
        ├── ObjectStorageError
        └── EmailDeliveryError
"""

from __future__ import annotations

from typing import Any


class PramanaError(Exception):
    """Base class for all Pramana errors.

    Subclasses should set :attr:`code` to a stable, machine-readable string
    that the API layer will surface to clients. The :attr:`message` is the
    human-readable description and may be safely logged.

    Attributes:
        code: Stable machine-readable error code.
        message: Human-readable description.
        context: Optional structured context for logging and observability.
    """

    code: str = "pramana_error"

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = context or {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# Domain errors — business-rule violations
# ---------------------------------------------------------------------------
class DomainError(PramanaError):
    """A business rule was violated."""

    code = "domain_error"


class InvalidStateTransitionError(DomainError):
    """Attempted state transition is not allowed by the state machine.

    Example: trying to ``submit`` an attempt that is not currently
    ``IN_PROGRESS``.
    """

    code = "invalid_state_transition"


class CooldownActiveError(DomainError):
    """Re-assignment of a course is blocked because cooldown is active.

    See FR8 and Section 4 of the resolved decisions document.
    """

    code = "cooldown_active"


class MaxAttemptsExceededError(DomainError):
    """All attempts for an assignment have been used.

    See FR9. The assignment is in :class:`AssignmentStatus.BLOCKED` and
    requires manager / compliance-admin intervention.
    """

    code = "max_attempts_exceeded"


class ConcurrentAssignmentError(DomainError):
    """The user already has an in-progress assignment.

    Per FR7, only one assignment may be ``IN_PROGRESS`` per user at a time.
    """

    code = "concurrent_assignment"


class SeparationOfDutiesError(DomainError):
    """SOX separation-of-duties rule was violated.

    Example: attempting to assign a course to a user who is also the
    course's content author.
    """

    code = "separation_of_duties"


# ---------------------------------------------------------------------------
# Generic errors
# ---------------------------------------------------------------------------
class NotFoundError(PramanaError):
    """A requested entity does not exist."""

    code = "not_found"


class ConflictError(PramanaError):
    """A uniqueness or optimistic-locking conflict occurred."""

    code = "conflict"


class DuplicatePackageError(ConflictError):
    """A consumable package with this ``(package_id, package_version)`` was
    already ingested.

    Delivery is idempotent on ``(package_id, package_version)`` (Mentible
    ADR-011 §6), so a re-push of an already-received package is a no-op
    conflict rather than a second draft.
    """

    code = "duplicate_package"


class ValidationError(PramanaError):
    """Input failed validation.

    Distinct from :class:`pydantic.ValidationError`: this is for application-
    level validation that runs after the schema layer.
    """

    code = "validation_error"


class PackageValidationError(ValidationError):
    """An incoming consumable-package manifest is structurally invalid.

    Raised while parsing the Mentible ADR-011 manifest — a missing required
    field, an empty ``modules`` list, an out-of-range pass threshold, etc.
    The package never becomes a draft.
    """

    code = "package_validation_error"


class PackageIntegrityError(ValidationError):
    """A consumable package failed signature or ``content_hash`` verification.

    Per Mentible ADR-011 §6, Pramana verifies the signature and content hash
    on arrival; a failure **quarantines** the package — it is never silently
    turned into a draft. Treat as tamper-evidence, not a transient error.
    """

    code = "package_integrity_error"


class AuthenticationError(PramanaError):
    """No valid credentials were presented."""

    code = "authentication_required"


class AuthorizationError(PramanaError):
    """Credentials are valid but the action is forbidden."""

    code = "forbidden"


# ---------------------------------------------------------------------------
# External service errors
# ---------------------------------------------------------------------------
class ExternalServiceError(PramanaError):
    """A downstream service failed.

    The cause may be transient; callers may retry with backoff.
    """

    code = "external_service_error"


class DatabaseError(ExternalServiceError):
    """The database is unavailable or returned an unexpected error."""

    code = "database_error"


class ObjectStorageError(ExternalServiceError):
    """Object storage (S3 or compatible) failed."""

    code = "object_storage_error"


class EmailDeliveryError(ExternalServiceError):
    """Outbound email delivery failed."""

    code = "email_delivery_error"
