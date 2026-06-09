"""The **Package Request** — Pramana's generation requirement for Mentible.

The *spec side* of the Mentible ADR-011 manifest: the inputs an author chooses
when commissioning content (US-PLATFORM-0003), which Mentible consumes (with
Pramana's definitions library) to manufacture and sign a Consumable Package.
This is the reverse direction of :mod:`pramana.domain.consumable_package` (which
reads what Mentible *returns*).

Pure — no database, no HTTP, no clock. :func:`build_package_request` validates a
decoded request body and returns an immutable :class:`PackageRequest`;
:meth:`PackageRequest.as_payload` renders the canonical JSON-able dict that the
outbound transport pushes to Mentible.

This module validates *structure* only. That every ``source_definitions[].ref``
resolves to a real clause anchor (AC4 — "no definition, no request") is checked
by :mod:`pramana.services.definitions_library` against the on-disk definitions,
which is I/O and therefore lives in the service layer.

Field → manifest mapping (the request's contract with Mentible, ADR-011 §4) is
documented in ``docs/user-stories/_templates/package-request.md`` §3.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeGuard

from pramana.exceptions import ValidationError

_DELIVERABLES = frozenset({"epub3", "pdf", "mp4"})
_VISUALS = frozenset({"animated_svg"})
_RISK_TIERS = frozenset({"low", "medium", "high"})
_STYLES = frozenset({"scenario-based", "recall"})


@dataclass(frozen=True, slots=True)
class RequestedClause:
    """One clause the request asks Mentible to cover (a definitions-library ref)."""

    framework: str
    clause: str
    ref: str | None = None


@dataclass(frozen=True, slots=True)
class Assessment:
    """Quiz parameters — becomes the manifest's ``quiz`` block."""

    pass_threshold_pct: int
    required: bool = True
    min_questions: int | None = None
    style: str = "scenario-based"


@dataclass(frozen=True, slots=True)
class PackageRequest:
    """An immutable, structurally validated commissioning request.

    The training-content slice of a user story expressed as a Mentible
    generation requirement. Pramana owns ``request_id``/``requested_by``;
    Mentible owns the resulting manifest's ``provenance``/``content_hash``/
    ``signature``/``package_id``/``package_version``.
    """

    framework: str
    title: str
    source_definitions: tuple[RequestedClause, ...]
    assessment: Assessment
    scope: Mapping[str, Any] = field(default_factory=dict)
    learning_objectives: tuple[str, ...] = ()
    constraints: Mapping[str, Any] = field(default_factory=dict)
    deliverables: tuple[str, ...] = ()
    visuals: tuple[str, ...] = ()
    satisfies_stories: tuple[str, ...] = ()
    course_id: uuid.UUID | None = None

    def as_payload(self, *, request_id: uuid.UUID, requested_by: str) -> dict[str, Any]:
        """Render the JSON-able request body pushed to Mentible.

        ``request_id``/``requested_by`` are stamped by the service (audit:
        *who* authorized the generation), not carried on the value object.
        """
        return {
            "request_id": str(request_id),
            "requested_by": requested_by,
            "framework": self.framework,
            "title": self.title,
            "scope": dict(self.scope),
            "source_definitions": [
                {"framework": c.framework, "clause": c.clause, "ref": c.ref}
                for c in self.source_definitions
            ],
            "learning_objectives": list(self.learning_objectives),
            "assessment": {
                "required": self.assessment.required,
                "pass_threshold_pct": self.assessment.pass_threshold_pct,
                "min_questions": self.assessment.min_questions,
                "style": self.assessment.style,
            },
            "constraints": dict(self.constraints),
            "deliverables": list(self.deliverables),
            "visuals": list(self.visuals),
            "satisfies_stories": list(self.satisfies_stories),
        }


def build_package_request(body: Mapping[str, Any]) -> PackageRequest:
    """Validate a decoded request body and build a :class:`PackageRequest`.

    Validates structure only — clause *resolvability* is the service's job.

    Raises:
        ValidationError: A required field is missing, has the wrong type, or
            holds an out-of-range / empty value.
    """
    if not isinstance(body, Mapping):
        raise ValidationError(
            "content request must be a JSON object", context={"type": type(body).__name__}
        )

    framework = _require_str(body, "framework")
    title = _require_str(body, "title")
    source_definitions = _parse_clauses(body)
    assessment = _parse_assessment(body)

    return PackageRequest(
        framework=framework,
        title=title,
        source_definitions=source_definitions,
        assessment=assessment,
        scope=_optional_object(body, "scope", _validate_scope),
        learning_objectives=_optional_str_tuple(body, "learning_objectives"),
        constraints=_optional_object(body, "constraints"),
        deliverables=_parse_enum_tuple(body, "deliverables", _DELIVERABLES),
        visuals=_parse_enum_tuple(body, "visuals", _VISUALS),
        satisfies_stories=_optional_str_tuple(body, "satisfies_stories"),
        course_id=_optional_uuid(body, "course_id"),
    )


def _parse_clauses(body: Mapping[str, Any]) -> tuple[RequestedClause, ...]:
    raw = body.get("source_definitions")
    if not _is_list(raw) or len(raw) == 0:
        raise ValidationError(
            "source_definitions must be a non-empty list",
            context={"field": "source_definitions"},
        )
    out: list[RequestedClause] = []
    for i, item in enumerate(raw):
        path = f"source_definitions[{i}]"
        if not isinstance(item, Mapping):
            raise ValidationError(f"{path} must be an object", context={"field": path})
        ref = item.get("ref")
        if ref is not None and (not isinstance(ref, str) or not ref.strip()):
            raise ValidationError(
                f"{path}.ref must be a non-empty string when present",
                context={"field": f"{path}.ref"},
            )
        out.append(
            RequestedClause(
                framework=_require_str(item, "framework", path=path),
                clause=_require_str(item, "clause", path=path),
                ref=ref,
            )
        )
    return tuple(out)


def _parse_assessment(body: Mapping[str, Any]) -> Assessment:
    raw = body.get("assessment")
    if not isinstance(raw, Mapping):
        raise ValidationError("assessment must be an object", context={"field": "assessment"})
    threshold = _require_int(raw, "pass_threshold_pct", minimum=0, maximum=100, path="assessment")
    min_questions = raw.get("min_questions")
    if min_questions is not None:
        min_questions = _require_int(raw, "min_questions", minimum=1, path="assessment")
    style = raw.get("style", "scenario-based")
    if style not in _STYLES:
        raise ValidationError(
            f"assessment.style must be one of {sorted(_STYLES)}",
            context={"field": "assessment.style", "value": style},
        )
    required = raw.get("required", True)
    if not isinstance(required, bool):
        raise ValidationError(
            "assessment.required must be a boolean",
            context={"field": "assessment.required"},
        )
    return Assessment(
        pass_threshold_pct=threshold,
        required=required,
        min_questions=min_questions,
        style=style,
    )


def _validate_scope(scope: Mapping[str, Any]) -> None:
    risk_tier = scope.get("risk_tier")
    if risk_tier is not None and risk_tier not in _RISK_TIERS:
        raise ValidationError(
            f"scope.risk_tier must be one of {sorted(_RISK_TIERS)}",
            context={"field": "scope.risk_tier", "value": risk_tier},
        )


# ---------------------------------------------------------------------------
# Field helpers (mirror the consumable_package validators' style)
# ---------------------------------------------------------------------------
def _require_str(obj: Mapping[str, Any], name: str, *, path: str | None = None) -> str:
    field_name = f"{path}.{name}" if path else name
    value = obj.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(
            f"field {field_name!r} must be a non-empty string",
            context={"field": field_name},
        )
    return value


def _require_int(
    obj: Mapping[str, Any],
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    path: str | None = None,
) -> int:
    field_name = f"{path}.{name}" if path else name
    value = obj.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(
            f"field {field_name!r} must be an integer", context={"field": field_name}
        )
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ValidationError(
            f"field {field_name!r} out of range [{minimum}, {maximum}]: {value}",
            context={"field": field_name, "value": value},
        )
    return value


def _optional_uuid(body: Mapping[str, Any], name: str) -> uuid.UUID | None:
    value = body.get(name)
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise ValidationError(
            f"field {name!r} must be a UUID", context={"field": name, "value": value}
        ) from exc


def _optional_object(body: Mapping[str, Any], name: str, validate: Any = None) -> Mapping[str, Any]:
    value = body.get(name)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValidationError(f"field {name!r} must be an object", context={"field": name})
    if validate is not None:
        validate(value)
    return value


def _optional_str_tuple(body: Mapping[str, Any], name: str) -> tuple[str, ...]:
    value = body.get(name)
    if value is None:
        return ()
    if not _is_list(value):
        raise ValidationError(f"field {name!r} must be a list of strings", context={"field": name})
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(
                f"field {name!r}[{i}] must be a non-empty string",
                context={"field": f"{name}[{i}]"},
            )
    return tuple(value)


def _parse_enum_tuple(
    body: Mapping[str, Any], name: str, allowed: frozenset[str]
) -> tuple[str, ...]:
    values = _optional_str_tuple(body, name)
    for v in values:
        if v not in allowed:
            raise ValidationError(
                f"field {name!r} value {v!r} must be one of {sorted(allowed)}",
                context={"field": name, "value": v},
            )
    return values


def _is_list(value: Any) -> TypeGuard[Sequence[Any]]:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes)
