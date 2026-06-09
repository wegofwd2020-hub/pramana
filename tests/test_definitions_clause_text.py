"""Unit tests for the clause-text reader (the in-process generation input)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pramana.exceptions import NotFoundError
from pramana.services import definitions_library

_DOC = """# Framework Reference: SOX (Sarbanes-Oxley)

Intro prose, not a clause.

### Management Assessment of Internal Controls

Management must assess and report on the effectiveness of internal controls.

```python
# a fenced ### inside code must not be treated as a heading
```

More body for this clause.

### Disclosure Controls

Separate clause body.
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "framework_sox.md").write_text(_DOC, encoding="utf-8")
    return tmp_path


def test_clause_text_returns_section_body(root: Path) -> None:
    text = definitions_library.clause_text(
        root, framework="sox", clause="management-assessment-of-internal-controls"
    )
    assert "Management must assess and report" in text
    assert "More body for this clause." in text
    # Stops at the next ### — does not bleed into the following clause.
    assert "Separate clause body" not in text


def test_clause_text_ignores_fenced_headings(root: Path) -> None:
    text = definitions_library.clause_text(
        root, framework="sox", clause="management-assessment-of-internal-controls"
    )
    # The fenced "### ..." line is body, not a section break.
    assert "must not be treated as a heading" in text


def test_clause_text_resolves_via_ref_fragment(root: Path) -> None:
    text = definitions_library.clause_text(
        root,
        framework="sox",
        clause="ignored-when-ref-present",
        ref="docs/frameworks/framework_sox.md#disclosure-controls",
    )
    assert text == "Separate clause body."


def test_clause_text_unknown_clause_raises(root: Path) -> None:
    with pytest.raises(NotFoundError):
        definitions_library.clause_text(root, framework="sox", clause="nonexistent")


def test_clause_text_unknown_framework_raises(root: Path) -> None:
    with pytest.raises(NotFoundError):
        definitions_library.clause_text(root, framework="hipaa", clause="anything")
