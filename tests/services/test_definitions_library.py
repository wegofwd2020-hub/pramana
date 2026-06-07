"""Tests for the definitions-library reader / clause resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from pramana.domain.package_request import build_package_request
from pramana.exceptions import NotFoundError, ValidationError
from pramana.services import definitions_library as dl

_FCPA = """# Framework Reference: FCPA (Foreign Corrupt Practices Act)

## 1. Framework Overview

### Anti-bribery
Text.

### Books and records
Text.

## 2. Why It Matters
```
### Not a heading (inside code fence)
```
"""

_SOX = "# Framework Reference: SOX\n\n### Section 404\nText.\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "framework_fcpa.md").write_text(_FCPA, encoding="utf-8")
    (tmp_path / "framework_sox.md").write_text(_SOX, encoding="utf-8")
    return tmp_path


class TestSlugify:
    def test_basic(self) -> None:
        assert dl.slugify("Anti-bribery") == "anti-bribery"

    def test_spaces_and_case(self) -> None:
        assert dl.slugify("Books and Records") == "books-and-records"

    def test_strips_punctuation(self) -> None:
        assert dl.slugify("1. Framework Overview") == "1-framework-overview"


class TestListFrameworks:
    def test_lists_each_doc(self, root: Path) -> None:
        codes = {f.code for f in dl.list_frameworks(root)}
        assert codes == {"fcpa", "sox"}

    def test_name_from_h1(self, root: Path) -> None:
        fcpa = next(f for f in dl.list_frameworks(root) if f.code == "fcpa")
        assert "FCPA" in fcpa.name


class TestListClauses:
    def test_only_h3_clauses(self, root: Path) -> None:
        clauses = {c.clause for c in dl.list_clauses(root, "fcpa")}
        assert clauses == {"anti-bribery", "books-and-records"}

    def test_ignores_headings_in_code_fence(self, root: Path) -> None:
        clauses = {c.clause for c in dl.list_clauses(root, "fcpa")}
        assert "not-a-heading-inside-code-fence" not in clauses

    def test_ref_anchor(self, root: Path) -> None:
        clause = next(c for c in dl.list_clauses(root, "fcpa") if c.clause == "anti-bribery")
        assert clause.ref.endswith("framework_fcpa.md#anti-bribery")

    def test_unknown_framework_raises(self, root: Path) -> None:
        with pytest.raises(NotFoundError):
            dl.list_clauses(root, "hipaa")


class TestResolves:
    def test_resolves_by_ref(self, root: Path) -> None:
        assert dl.resolves(
            root, framework="fcpa", clause="anti-bribery",
            ref="docs/frameworks/framework_fcpa.md#anti-bribery",
        )

    def test_resolves_by_clause_slug_when_no_ref(self, root: Path) -> None:
        assert dl.resolves(root, framework="fcpa", clause="Books and records", ref=None)

    def test_unknown_anchor_does_not_resolve(self, root: Path) -> None:
        assert not dl.resolves(
            root, framework="fcpa", clause="bribery",
            ref="docs/frameworks/framework_fcpa.md#made-up",
        )

    def test_unknown_framework_does_not_resolve(self, root: Path) -> None:
        assert not dl.resolves(root, framework="gdpr", clause="x", ref=None)


class TestValidateRequestClauses:
    def test_passes_when_all_resolve(self, root: Path) -> None:
        req = build_package_request(
            {
                "framework": "fcpa",
                "title": "t",
                "source_definitions": [
                    {"framework": "fcpa", "clause": "anti-bribery",
                     "ref": "docs/frameworks/framework_fcpa.md#anti-bribery"}
                ],
                "assessment": {"pass_threshold_pct": 80},
            }
        )
        dl.validate_request_clauses(root, req)  # no raise

    def test_raises_and_lists_unresolved(self, root: Path) -> None:
        req = build_package_request(
            {
                "framework": "fcpa",
                "title": "t",
                "source_definitions": [
                    {"framework": "fcpa", "clause": "anti-bribery",
                     "ref": "docs/frameworks/framework_fcpa.md#anti-bribery"},
                    {"framework": "fcpa", "clause": "ghost",
                     "ref": "docs/frameworks/framework_fcpa.md#ghost"},
                ],
                "assessment": {"pass_threshold_pct": 80},
            }
        )
        with pytest.raises(ValidationError) as exc:
            dl.validate_request_clauses(root, req)
        assert exc.value.context["unresolved"] == [
            "docs/frameworks/framework_fcpa.md#ghost"
        ]
