"""Guard the 32-char limit ``alembic_version.version_num`` actually has.

``alembic_version.version_num`` is ``VARCHAR(32)`` (Alembic's own schema, not
ours). A revision id longer than that does not fail loudly at the boundary —
it fails with ``StringDataRightTruncationError`` partway through applying it,
which rolls back the *entire* ``0001..N`` upgrade transaction. This already
happened once on this branch and, until now, was recorded only in ``0012``'s
docstring (its id was shortened from ``"0012_content_draft_video_attestation"``,
37 chars, to ``"0012_video_attestation"``, 23). Nothing enforced it going
forward.

Migration files are not importable by dotted name (``alembic/versions`` is not
a package, and every filename starts with a digit), so this reads the
``revision = "..."`` assignment out of the source text with a regex rather
than importing the module.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"

#: alembic_version.version_num is VARCHAR(32) — Alembic's own migration table,
#: not something this schema defines or can widen without also changing
#: Alembic's bookkeeping.
_MAX_REVISION_ID_LEN = 32

#: Matches `revision: str = "..."` or `revision = "..."` (single or double
#: quoted), the way every file in alembic/versions/ declares it.
_REVISION_RE = re.compile(
    r"""^revision\s*(?::\s*str\s*)?=\s*(?P<q>['"])(?P<id>.*?)(?P=q)\s*$""",
    re.MULTILINE,
)


def _migration_files() -> list[Path]:
    return sorted(_VERSIONS_DIR.glob("*.py"))


def _revision_id(path: Path) -> str:
    match = _REVISION_RE.search(path.read_text())
    assert match is not None, f'{path.name}: no `revision = "..."` assignment found'
    return match.group("id")


class TestRevisionIdsFitTheAlembicVersionColumn:
    def test_every_migration_file_declares_a_revision(self) -> None:
        files = _migration_files()
        assert files, "no migration files found under alembic/versions/"

    @pytest.mark.parametrize(
        "path", _migration_files(), ids=lambda p: p.name if isinstance(p, Path) else str(p)
    )
    def test_revision_id_is_at_most_32_chars(self, path: Path) -> None:
        revision_id = _revision_id(path)
        assert len(revision_id) <= _MAX_REVISION_ID_LEN, (
            f"{path.name}: revision id {revision_id!r} is {len(revision_id)} chars, "
            f"over the {_MAX_REVISION_ID_LEN}-char limit of alembic_version.version_num "
            f"(VARCHAR(32)) — this rolls back the whole upgrade transaction with "
            f"StringDataRightTruncationError instead of failing at plan time."
        )
