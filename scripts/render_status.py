#!/usr/bin/env python3
"""Render the README status table from ``project-status.yaml``.

The README table used to be maintained by hand alongside the manifest, and it
drifted: for three weeks it claimed the learner runtime did not exist, weeks
after it shipped. Duplicated state with no check is state that rots, so the
manifest is now the single source and this script renders the table from it.

Usage::

    python scripts/render_status.py            # rewrite the README block
    python scripts/render_status.py --check    # exit 1 if it is out of date

``make status`` runs the first; ``tests/test_project_status.py`` runs the
second, so drift fails the suite rather than shipping.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "project-status.yaml"
README = ROOT / "README.md"

BEGIN = "<!-- BEGIN GENERATED: status -->"
END = "<!-- END GENERATED: status -->"

#: Manifest status -> the cell the README shows. Keys are the only values the
#: manifest may use; an unknown one is a typo and should fail loudly rather
#: than render a blank cell.
STATUS_CELLS = {
    "done": "✅ Complete",
    "in-progress": "🚧 In progress",
    "pending": "⏳ Planned",
}


def load_features(manifest: Path = MANIFEST) -> list[dict[str, Any]]:
    """Return the manifest's feature list, validated."""
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    features = data.get("features")
    if not features:
        raise ValueError(f"{manifest.name} declares no features")

    seen: set[str] = set()
    for feature in features:
        for key in ("id", "name", "status"):
            if not feature.get(key):
                raise ValueError(f"feature {feature!r} is missing '{key}'")
        if feature["status"] not in STATUS_CELLS:
            raise ValueError(
                f"feature {feature['id']!r} has unknown status {feature['status']!r}; "
                f"expected one of {', '.join(sorted(STATUS_CELLS))}"
            )
        if feature["id"] in seen:
            raise ValueError(f"duplicate feature id {feature['id']!r}")
        seen.add(feature["id"])
    return list(features)


def render_table(features: list[dict[str, Any]]) -> str:
    """Render the markdown table, in manifest order."""
    lines = ["| Deliverable | Status |", "|---|---|"]
    lines += [f"| {f['name']} | {STATUS_CELLS[f['status']]} |" for f in features]
    return "\n".join(lines)


def render_block(features: list[dict[str, Any]]) -> str:
    """The full marker-delimited block the README should contain."""
    return f"{BEGIN}\n\n{render_table(features)}\n\n{END}"


def replace_block(readme_text: str, block: str) -> str:
    """Swap the marked region of the README for ``block``."""
    start = readme_text.find(BEGIN)
    end = readme_text.find(END)
    if start == -1 or end == -1:
        raise ValueError(f"README is missing the {BEGIN} / {END} markers")
    return readme_text[:start] + block + readme_text[end + len(END) :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the README is up to date instead of rewriting it",
    )
    args = parser.parse_args(argv)

    block = render_block(load_features())
    current = README.read_text(encoding="utf-8")
    updated = replace_block(current, block)

    if args.check:
        if current != updated:
            print(
                "README status table is out of date with project-status.yaml.\n"
                "Run `make status` (or `python scripts/render_status.py`) and commit.",
                file=sys.stderr,
            )
            return 1
        print("README status table is up to date.")
        return 0

    if current == updated:
        print("README status table already up to date.")
        return 0
    README.write_text(updated, encoding="utf-8")
    print(f"Rewrote the status table in {README.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
