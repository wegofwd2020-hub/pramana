"""The Mentible **Consumable Package** — Pramana's side of the handoff contract.

Mentible ADR-011 (``StudyBuddy_SelfLearner/docs/adr/ADR-011-pramana-compliance-
integration.md``) defines the integration boundary as an **artifact handoff,
not a service call**: Mentible *ships a consumable* and Pramana *ingests* it.
The unit of exchange is a versioned, signed JSON **manifest** (ADR-011 §4). This
module is Pramana's authoritative reader for that manifest.

It is **pure** — no database, no HTTP, no I/O, no clock. Given a decoded
manifest (a ``dict`` parsed from JSON) it:

* :func:`parse_manifest` — validates structure and returns an immutable
  :class:`ConsumablePackage` value object (raising
  :class:`~pramana.exceptions.PackageValidationError` on a malformed manifest);
* :func:`verify_content_hash` — recomputes the canonical content hash and
  checks it against the declared ``content_hash``;
* :func:`verify_signature` — delegates to an injected
  :class:`SignatureVerifier` (key custody lives outside the domain);
* :func:`verify_package` — the two integrity checks together. A failure raises
  :class:`~pramana.exceptions.PackageIntegrityError`, which the ingestion
  service treats as **quarantine** — never a silently published draft
  (ADR-011 §6).

Trust model: an arrival is *untrusted draft* until a human approves it
(ADR-011 §3). This module only establishes that the bytes are well-formed and
intact; it does **not** establish that the content is correct — that is the
human approver's job, downstream (:mod:`pramana.domain.content_approval`).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pramana.exceptions import PackageIntegrityError, PackageValidationError

_HASH_PREFIX = "sha256:"


# ---------------------------------------------------------------------------
# Value objects (the manifest, §4)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Provenance:
    """How the package was produced — audit + drift detection (ADR-011 §4).

    ``generated_at`` is timezone-aware; the generating engine stamps it.
    """

    engine: str
    model: str
    provider: str
    prompt_version: str
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """A definition clause the package covers — traceability back to Pramana's
    library so a reviewer verifies content against the regulation, not vibes."""

    framework: str
    clause: str
    ref: str | None = None


@dataclass(frozen=True, slots=True)
class ConsumablePackage:
    """An immutable, validated view of a received consumable-package manifest.

    Only the fields Pramana needs to *ingest and trace* are promoted to typed
    attributes. The training content itself (``modules`` / ``quiz``) is kept as
    the raw mapping it arrived as: it is stored verbatim on the draft body and
    destructured into :class:`~pramana.db.models.course.Question` /
    ``AnswerOption`` at publish time (:func:`pramana.domain.publication.
    materialize_quiz`). Keeping it verbatim also means the content hash we verify
    is over *exactly* the bytes that arrived.

    Attributes:
        package_id: Stable id for this consumable.
        package_version: Bumped by Mentible on re-generation. Delivery is
            idempotent on ``(package_id, package_version)``.
        request_id: The originating Package Request's id, echoed back by Mentible
            so Pramana can correlate the arrival with the commission that asked
            for it (ADR-011 §4 ``request_id``). Optional: a package may arrive
            without one (e.g. hand-delivered), in which case the request loop is
            simply not closed for it.
        title: Human-readable package title.
        frameworks: Which standards this package covers (e.g. ``["sox"]``).
        source_definitions: Clause-level traceability to the definitions library.
        provenance: Engine/model/provider/prompt/timestamp.
        declared_content_hash: The ``content_hash`` asserted in the manifest
            (``"sha256:…"``), verified against :func:`compute_content_hash`.
        modules: The deck/lessons, verbatim.
        quiz: The assessment, verbatim.
        assets: Visual asset references (animated SVG, images).
        artifacts: Compiled deliverable references (epub3/pdf/mp4).
        signature: Manifest signature, verified by a :class:`SignatureVerifier`.
        content_body_payload: Canonical bytes the content hash is computed over
            (``{"modules": …, "quiz": …}``). Retained so verification never
            re-canonicalizes ambiguously.
        signing_payload: Canonical bytes the signature is verified over (the
            whole manifest minus the ``signature`` field).
    """

    package_id: uuid.UUID
    package_version: int
    request_id: uuid.UUID | None
    title: str
    frameworks: tuple[str, ...]
    source_definitions: tuple[SourceDefinition, ...]
    provenance: Provenance
    declared_content_hash: str
    modules: tuple[Mapping[str, Any], ...]
    quiz: Mapping[str, Any]
    assets: tuple[Mapping[str, Any], ...]
    artifacts: tuple[Mapping[str, Any], ...]
    signature: str
    content_body_payload: bytes = field(repr=False)
    signing_payload: bytes = field(repr=False)


# ---------------------------------------------------------------------------
# Canonicalisation + hashing
# ---------------------------------------------------------------------------
def canonical_json(obj: Any) -> bytes:
    """Serialize ``obj`` to canonical JSON bytes (sorted keys, no whitespace).

    Both sides of the boundary must canonicalize identically for the hash and
    signature to agree, so this is the single definition of "canonical".
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def compute_content_hash(content_body_payload: bytes) -> str:
    """Return the ``"sha256:…"`` hash of the canonical content body."""
    return _HASH_PREFIX + hashlib.sha256(content_body_payload).hexdigest()


# ---------------------------------------------------------------------------
# Parsing / validation (§4)
# ---------------------------------------------------------------------------
def parse_manifest(manifest: Mapping[str, Any]) -> ConsumablePackage:
    """Validate a decoded manifest and build a :class:`ConsumablePackage`.

    This checks *structure*, not *integrity* — call :func:`verify_package`
    afterwards to check the signature and content hash.

    Raises:
        PackageValidationError: A required field is missing, has the wrong
            type, or holds an out-of-range / empty value.
    """
    if not isinstance(manifest, Mapping):
        raise PackageValidationError(
            "manifest must be a JSON object",
            context={"type": type(manifest).__name__},
        )

    package_id = _require_uuid(manifest, "package_id")
    package_version = _require_int(manifest, "package_version", minimum=1)
    request_id = _optional_uuid(manifest, "request_id")
    title = _require_str(manifest, "title")
    frameworks = tuple(_require_str_list(manifest, "frameworks", allow_empty=False))
    source_definitions = _parse_source_definitions(manifest)
    provenance = _parse_provenance(manifest)
    declared_content_hash = _require_hash(manifest, "content_hash")
    modules = _require_object_list(manifest, "modules", allow_empty=False)
    quiz = _parse_quiz(manifest)
    assets = _require_object_list(manifest, "assets", allow_empty=True)
    artifacts = _require_object_list(manifest, "artifacts", allow_empty=True)
    signature = _require_str(manifest, "signature")

    content_body_payload = canonical_json({"modules": modules, "quiz": quiz})
    signing_payload = canonical_json({k: v for k, v in manifest.items() if k != "signature"})

    return ConsumablePackage(
        package_id=package_id,
        package_version=package_version,
        request_id=request_id,
        title=title,
        frameworks=frameworks,
        source_definitions=source_definitions,
        provenance=provenance,
        declared_content_hash=declared_content_hash,
        modules=tuple(modules),
        quiz=quiz,
        assets=tuple(assets),
        artifacts=tuple(artifacts),
        signature=signature,
        content_body_payload=content_body_payload,
        signing_payload=signing_payload,
    )


def _parse_provenance(manifest: Mapping[str, Any]) -> Provenance:
    raw = _require_object(manifest, "provenance")
    return Provenance(
        engine=_require_str(raw, "engine", path="provenance"),
        model=_require_str(raw, "model", path="provenance"),
        provider=_require_str(raw, "provider", path="provenance"),
        prompt_version=_require_str(raw, "prompt_version", path="provenance"),
        generated_at=_require_datetime(raw, "generated_at", path="provenance"),
    )


def _parse_source_definitions(
    manifest: Mapping[str, Any],
) -> tuple[SourceDefinition, ...]:
    raw = _require_object_list(manifest, "source_definitions", allow_empty=False)
    out: list[SourceDefinition] = []
    for i, item in enumerate(raw):
        path = f"source_definitions[{i}]"
        ref = item.get("ref")
        if ref is not None and not isinstance(ref, str):
            raise PackageValidationError(
                f"{path}.ref must be a string when present",
                context={"field": f"{path}.ref"},
            )
        out.append(
            SourceDefinition(
                framework=_require_str(item, "framework", path=path),
                clause=_require_str(item, "clause", path=path),
                ref=ref,
            )
        )
    return tuple(out)


def _parse_quiz(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    quiz = _require_object(manifest, "quiz")
    _require_int(quiz, "pass_threshold_pct", minimum=0, maximum=100, path="quiz")
    questions = quiz.get("questions")
    if not isinstance(questions, Sequence) or isinstance(questions, str | bytes):
        raise PackageValidationError(
            "quiz.questions must be a list", context={"field": "quiz.questions"}
        )
    if len(questions) == 0:
        raise PackageValidationError(
            "quiz.questions must not be empty", context={"field": "quiz.questions"}
        )
    return quiz


# ---------------------------------------------------------------------------
# Integrity verification (§6)
# ---------------------------------------------------------------------------
@runtime_checkable
class SignatureVerifier(Protocol):
    """Verifies a package signature. The concrete scheme and key custody live
    outside the domain (ADR-011 §10 leaves the signing scheme open)."""

    def verify(self, *, signed_payload: bytes, signature: str) -> bool:
        """Return True iff ``signature`` is valid for ``signed_payload``."""
        ...


def verify_content_hash(package: ConsumablePackage) -> None:
    """Check the declared ``content_hash`` against the recomputed canonical hash.

    Raises:
        PackageIntegrityError: The recomputed hash does not match — quarantine.
    """
    actual = compute_content_hash(package.content_body_payload)
    if not _constant_time_eq(actual, package.declared_content_hash):
        raise PackageIntegrityError(
            "content_hash mismatch: recomputed hash does not match manifest",
            context={
                "package_id": str(package.package_id),
                "package_version": package.package_version,
                "declared": package.declared_content_hash,
                "actual": actual,
            },
        )


def verify_signature(package: ConsumablePackage, verifier: SignatureVerifier) -> None:
    """Verify the manifest signature via ``verifier``.

    Raises:
        PackageIntegrityError: The signature is invalid — quarantine.
    """
    if not verifier.verify(signed_payload=package.signing_payload, signature=package.signature):
        raise PackageIntegrityError(
            "invalid package signature",
            context={
                "package_id": str(package.package_id),
                "package_version": package.package_version,
            },
        )


def verify_package(package: ConsumablePackage, verifier: SignatureVerifier) -> None:
    """Run both integrity checks (signature, then content hash).

    Signature first: it covers the whole manifest including the declared
    ``content_hash``, so a valid signature means the hash field itself is
    trustworthy before we compare against it.

    Raises:
        PackageIntegrityError: Either check failed — quarantine the package.
    """
    verify_signature(package, verifier)
    verify_content_hash(package)


# ---------------------------------------------------------------------------
# Field validators
# ---------------------------------------------------------------------------
def _qualified(name: str, path: str | None) -> str:
    return f"{path}.{name}" if path else name


def _require(obj: Mapping[str, Any], name: str, *, path: str | None = None) -> Any:
    if name not in obj or obj[name] is None:
        field_name = _qualified(name, path)
        raise PackageValidationError(
            f"missing required field {field_name!r}",
            context={"field": field_name},
        )
    return obj[name]


def _require_str(obj: Mapping[str, Any], name: str, *, path: str | None = None) -> str:
    value = _require(obj, name, path=path)
    field_name = _qualified(name, path)
    if not isinstance(value, str) or not value.strip():
        raise PackageValidationError(
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
    value = _require(obj, name, path=path)
    field_name = _qualified(name, path)
    # bool is an int subclass — reject it explicitly.
    if not isinstance(value, int) or isinstance(value, bool):
        raise PackageValidationError(
            f"field {field_name!r} must be an integer",
            context={"field": field_name},
        )
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise PackageValidationError(
            f"field {field_name!r} out of range [{minimum}, {maximum}]: {value}",
            context={"field": field_name, "value": value},
        )
    return value


def _require_uuid(obj: Mapping[str, Any], name: str) -> uuid.UUID:
    value = _require_str(obj, name)
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise PackageValidationError(
            f"field {name!r} must be a UUID string",
            context={"field": name, "value": value},
        ) from exc


def _optional_uuid(obj: Mapping[str, Any], name: str) -> uuid.UUID | None:
    """Parse an optional UUID field; ``None`` if absent, error if malformed."""
    if obj.get(name) is None:
        return None
    return _require_uuid(obj, name)


def _require_datetime(obj: Mapping[str, Any], name: str, *, path: str | None = None) -> datetime:
    value = _require_str(obj, name, path=path)
    field_name = _qualified(name, path)
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise PackageValidationError(
            f"field {field_name!r} must be an ISO-8601 datetime",
            context={"field": field_name, "value": value},
        ) from exc
    if parsed.tzinfo is None:
        raise PackageValidationError(
            f"field {field_name!r} must be timezone-aware",
            context={"field": field_name, "value": value},
        )
    return parsed


def _require_hash(obj: Mapping[str, Any], name: str) -> str:
    value = _require_str(obj, name)
    if not value.startswith(_HASH_PREFIX) or len(value) != len(_HASH_PREFIX) + 64:
        raise PackageValidationError(
            f"field {name!r} must be a {_HASH_PREFIX}<64 hex> digest",
            context={"field": name, "value": value},
        )
    return value


def _require_str_list(obj: Mapping[str, Any], name: str, *, allow_empty: bool) -> list[str]:
    value = _require(obj, name)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise PackageValidationError(
            f"field {name!r} must be a list of strings", context={"field": name}
        )
    if not allow_empty and len(value) == 0:
        raise PackageValidationError(f"field {name!r} must not be empty", context={"field": name})
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise PackageValidationError(
                f"field {name!r}[{i}] must be a non-empty string",
                context={"field": f"{name}[{i}]"},
            )
    return list(value)


def _require_object(
    obj: Mapping[str, Any], name: str, *, path: str | None = None
) -> Mapping[str, Any]:
    value = _require(obj, name, path=path)
    field_name = _qualified(name, path)
    if not isinstance(value, Mapping):
        raise PackageValidationError(
            f"field {field_name!r} must be an object",
            context={"field": field_name},
        )
    return value


def _require_object_list(
    obj: Mapping[str, Any], name: str, *, allow_empty: bool
) -> list[Mapping[str, Any]]:
    value = _require(obj, name) if not allow_empty else obj.get(name, [])
    if value is None:
        value = []
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise PackageValidationError(f"field {name!r} must be a list", context={"field": name})
    if not allow_empty and len(value) == 0:
        raise PackageValidationError(f"field {name!r} must not be empty", context={"field": name})
    for i, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise PackageValidationError(
                f"field {name!r}[{i}] must be an object",
                context={"field": f"{name}[{i}]"},
            )
    return list(value)


def _constant_time_eq(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a, b)
