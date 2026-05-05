"""Tests for :mod:`pramana.exceptions`."""

from __future__ import annotations

import pytest

from pramana.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConcurrentAssignmentError,
    ConflictError,
    CooldownActiveError,
    DatabaseError,
    DomainError,
    EmailDeliveryError,
    ExternalServiceError,
    InvalidStateTransitionError,
    MaxAttemptsExceededError,
    NotFoundError,
    ObjectStorageError,
    PramanaError,
    SeparationOfDutiesError,
    ValidationError,
)


class TestExceptionHierarchy:
    """Inheritance relationships between exception classes."""

    @pytest.mark.parametrize(
        "subclass",
        [
            DomainError,
            NotFoundError,
            ConflictError,
            ValidationError,
            AuthenticationError,
            AuthorizationError,
            ExternalServiceError,
        ],
    )
    def test_top_level_errors_inherit_from_base(
        self, subclass: type[PramanaError]
    ) -> None:
        """All top-level errors derive from :class:`PramanaError`."""
        assert issubclass(subclass, PramanaError)

    @pytest.mark.parametrize(
        "subclass",
        [
            InvalidStateTransitionError,
            CooldownActiveError,
            MaxAttemptsExceededError,
            ConcurrentAssignmentError,
            SeparationOfDutiesError,
        ],
    )
    def test_domain_subclasses_inherit_from_domain_error(
        self, subclass: type[DomainError]
    ) -> None:
        """Domain subclasses derive from :class:`DomainError`."""
        assert issubclass(subclass, DomainError)
        assert issubclass(subclass, PramanaError)

    @pytest.mark.parametrize(
        "subclass",
        [DatabaseError, ObjectStorageError, EmailDeliveryError],
    )
    def test_external_subclasses_inherit_from_external(
        self, subclass: type[ExternalServiceError]
    ) -> None:
        """External-service subclasses derive from :class:`ExternalServiceError`."""
        assert issubclass(subclass, ExternalServiceError)


class TestPramanaError:
    """Behavior of the :class:`PramanaError` base class."""

    def test_carries_message(self) -> None:
        """The message is stored on the instance and as the exception args."""
        err = PramanaError("something broke")
        assert err.message == "something broke"
        assert str(err) == "something broke"

    def test_carries_optional_context(self) -> None:
        """Optional structured context is stored as a dict."""
        err = PramanaError("boom", context={"user_id": "u-1", "course_id": "c-7"})
        assert err.context == {"user_id": "u-1", "course_id": "c-7"}

    def test_default_context_is_empty_dict(self) -> None:
        """When no context is supplied, ``context`` is an empty dict (not None)."""
        err = PramanaError("boom")
        assert err.context == {}

    def test_subclasses_have_distinct_codes(self) -> None:
        """Each subclass has a distinct, machine-readable code."""
        codes = {
            PramanaError.code,
            DomainError.code,
            InvalidStateTransitionError.code,
            CooldownActiveError.code,
            MaxAttemptsExceededError.code,
            ConcurrentAssignmentError.code,
            SeparationOfDutiesError.code,
            NotFoundError.code,
            ConflictError.code,
            ValidationError.code,
            AuthenticationError.code,
            AuthorizationError.code,
            ExternalServiceError.code,
            DatabaseError.code,
            ObjectStorageError.code,
            EmailDeliveryError.code,
        }
        # All codes must be unique (no two classes share a code).
        assert len(codes) == 16

    def test_repr_includes_code_and_message(self) -> None:
        """``repr`` is informative for logs."""
        err = NotFoundError("user not found")
        rendered = repr(err)
        assert "NotFoundError" in rendered
        assert "not_found" in rendered
        assert "user not found" in rendered
