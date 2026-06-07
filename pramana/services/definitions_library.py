"""The definitions library — Pramana's "law" picker and clause resolver.

Pramana owns the regulatory definitions (Mentible ADR-011 §1): a directory of
``framework_<code>.md`` reference docs whose headings are the citable clause
anchors. This module feeds the commissioning UI's framework/clause pickers
(US-PLATFORM-0003) and enforces AC4 — *"no definition, no request"*: a Package
Request whose ``source_definitions[].ref`` does not resolve to a real anchor in
the library cannot be submitted.

It reads files (so it is a service, not pure domain), but the slug/anchor logic
is pure and isolated in :func:`slugify`. The library root is passed in by the
caller (the dependency provider supplies ``Settings.definitions_root``) so tests
can point it at a fixture directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pramana.domain.package_request import PackageRequest
from pramana.exceptions import NotFoundError, ValidationError

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_CLAUSE_LEVEL = 3  # "### Heading" — the definition clauses live at h3.
_SLUG_STRIP_RE = re.compile(r"[^\w\- ]+")
_SLUG_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class FrameworkInfo:
    """A framework reference doc, for the picker."""

    code: str
    name: str
    doc: str


@dataclass(frozen=True, slots=True)
class ClauseInfo:
    """A citable clause anchor within a framework doc."""

    clause: str
    title: str
    ref: str


def slugify(text: str) -> str:
    """GitHub-style heading anchor: lowercase, punctuation dropped, spaces → ``-``."""
    lowered = text.strip().lower()
    cleaned = _SLUG_STRIP_RE.sub("", lowered)
    return _SLUG_SPACE_RE.sub("-", cleaned.strip())


def _doc_name(framework: str) -> str:
    return f"framework_{framework.strip().lower()}.md"


def _doc_path(root: Path, framework: str) -> Path:
    return root / _doc_name(framework)


def list_frameworks(root: Path) -> list[FrameworkInfo]:
    """List the frameworks in the library (one per ``framework_*.md``)."""
    out: list[FrameworkInfo] = []
    for path in sorted(root.glob("framework_*.md")):
        code = path.stem.removeprefix("framework_")
        out.append(FrameworkInfo(code=code, name=_title_of(path) or code, doc=path.name))
    return out


def list_clauses(root: Path, framework: str) -> list[ClauseInfo]:
    """List a framework's citable clause anchors (its ``###`` definitions).

    Raises:
        NotFoundError: No ``framework_<framework>.md`` in the library.
    """
    path = _doc_path(root, framework)
    if not path.is_file():
        raise NotFoundError(
            "framework not found in definitions library",
            context={"framework": framework},
        )
    doc_ref = f"{root.name}/{path.name}"
    out: list[ClauseInfo] = []
    for level, title in _headings(path):
        if level != _CLAUSE_LEVEL:
            continue
        slug = slugify(title)
        out.append(ClauseInfo(clause=slug, title=title, ref=f"{doc_ref}#{slug}"))
    return out


def resolves(root: Path, *, framework: str, clause: str, ref: str | None) -> bool:
    """True iff the clause anchor exists in the framework's doc.

    The anchor checked is the fragment of ``ref`` when present, else the slug of
    ``clause``. Resolution is against *all* headings in the doc (an anchor is an
    anchor), not only the ``###`` clauses the picker advertises.
    """
    path = _doc_path(root, framework)
    if not path.is_file():
        return False
    anchor = _fragment(ref) if ref else slugify(clause)
    if not anchor:
        return False
    return anchor in _anchors(path)


def validate_request_clauses(root: Path, request: PackageRequest) -> None:
    """Enforce AC4 — every cited clause must resolve, else the request is rejected.

    Raises:
        ValidationError: One or more ``source_definitions`` do not resolve. The
            context lists every unresolved ref so the author can fix them all.
    """
    unresolved = [
        c.ref or f"{c.framework}#{slugify(c.clause)}"
        for c in request.source_definitions
        if not resolves(root, framework=c.framework, clause=c.clause, ref=c.ref)
    ]
    if unresolved:
        raise ValidationError(
            "one or more cited clauses do not resolve in the definitions library",
            context={"unresolved": unresolved},
        )


# ---------------------------------------------------------------------------
# File reading (cached by path — the library is read-only at runtime)
# ---------------------------------------------------------------------------
def _fragment(ref: str) -> str:
    _, _, frag = ref.partition("#")
    return frag.strip().lower()


def _headings(path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    in_code = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _HEADING_RE.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2)))
    return out


@lru_cache(maxsize=64)
def _anchors(path: Path) -> frozenset[str]:
    return frozenset(slugify(title) for _, title in _headings(path))


def _title_of(path: Path) -> str | None:
    for level, title in _headings(path):
        if level == 1:
            # "Framework Reference: FCPA (...)" → "FCPA (...)".
            return title.split(":", 1)[1].strip() if ":" in title else title
    return None
