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


def clause_text(root: Path, *, framework: str, clause: str, ref: str | None = None) -> str:
    """Return the prose body of a clause — the input for in-process generation.

    Resolves the clause's heading anchor (the fragment of ``ref`` when present,
    else the slug of ``clause``) and returns the text between that heading and
    the next heading of the same or higher level, code fences excluded. This is
    the source material a generator (ADR-013) drafts a quiz / summary *from*, so
    every claim it makes is grounded in the definitions library — Pramana's
    source of truth — not the model's parametric memory.

    Raises:
        NotFoundError: No ``framework_<framework>.md`` doc, or the anchor does
            not resolve to a heading in it.
    """
    path = _doc_path(root, framework)
    if not path.is_file():
        raise NotFoundError(
            "framework not found in definitions library",
            context={"framework": framework},
        )
    anchor = _fragment(ref) if ref else slugify(clause)
    body = _section_body(path, anchor)
    if body is None:
        raise NotFoundError(
            "clause anchor not found in framework doc",
            context={"framework": framework, "clause": clause, "anchor": anchor},
        )
    return body


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


@lru_cache(maxsize=64)
def _headings(path: Path) -> tuple[tuple[int, str], ...]:
    """Parse a framework doc's headings once and memoise (the library is
    read-only at runtime). Cached here at the I/O boundary so ``list_clauses``,
    ``list_frameworks``, and ``_anchors`` all reuse a single file read per doc.
    Returns a tuple so the cached value can't be mutated by a caller."""
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
    return tuple(out)


def _anchors(path: Path) -> frozenset[str]:
    return frozenset(slugify(title) for _, title in _headings(path))


@lru_cache(maxsize=64)
def _sections(path: Path) -> dict[str, str]:
    """Map each heading's slug → the prose body beneath it (memoised).

    A section runs from its heading to the next heading of the same or higher
    level. Code fences are preserved verbatim in the body but their ``#`` lines
    never count as headings. Cached at the I/O boundary like :func:`_headings`.
    """
    sections: dict[str, str] = {}
    stack: list[tuple[int, str, list[str]]] = []  # (level, slug, body lines)

    def _close(down_to_level: int) -> None:
        while stack and stack[-1][0] >= down_to_level:
            _level, slug, lines = stack.pop()
            sections[slug] = "\n".join(lines).strip()

    in_code = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            if stack:
                stack[-1][2].append(line)
            continue
        m = None if in_code else _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            _close(level)
            stack.append((level, slugify(m.group(2)), []))
        elif stack:
            stack[-1][2].append(line)
    _close(0)
    return sections


def _section_body(path: Path, anchor: str) -> str | None:
    """Prose body under the heading whose slug is ``anchor`` (``None`` if absent)."""
    return _sections(path).get(anchor)


def _title_of(path: Path) -> str | None:
    for level, title in _headings(path):
        if level == 1:
            # "Framework Reference: FCPA (...)" → "FCPA (...)".
            return title.split(":", 1)[1].strip() if ":" in title else title
    return None
