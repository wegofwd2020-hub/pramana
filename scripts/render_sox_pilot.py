"""Render the SOX pilot segment: one clip per narration line, concatenated.

Manual by necessity — CI installs ``.[dev]`` only, so it has no torch and no
weights. The composition and the capability check are unit-tested; the render
is run by hand and its numbers recorded in ``docs/sox-video-pilot-run.md``.

Usage::

    python scripts/render_sox_pilot.py --dry-run     # plan only; no torch
    python scripts/render_sox_pilot.py \\
        --out /tmp/sox-pilot.mp4 --json /tmp/sox-pilot.json --seed 9071
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pramana.domain.video_generation import build_scene_briefs

#: The local-preview role's ceiling on a single scene's render duration. It is
#: reused here as the whole pilot segment's total-duration budget: catching a
#: rejected geometry at plan time costs a second, catching it an hour into a
#: render costs an hour.
MAX_DURATION_S = 10.0

#: Five lines at the 2.0 s default totals exactly 10.0 s — inside the cap,
#: but with zero headroom. Adding a line, or raising ``--shot-duration``,
#: pushes the segment over and ``build_plan`` refuses it before anything loads.
SCRIPT_LINES = [
    "Every internal control over financial reporting has a named owner.",
    "Evidence is recorded at the moment the control runs.",
    "The record is what the external auditor will examine under section 404.",
    "A missing owner is itself a finding, not a footnote.",
    "This pilot renders that message as a short compliance clip.",
]


@dataclass(frozen=True)
class Plan:
    """A composed, capability-checked render plan: one brief per scene."""

    briefs: list[Any]
    clause_title: str
    shot_duration_s: float

    @property
    def total_duration_s(self) -> float:
        return float(sum(s.duration_s for b in self.briefs for s in b.shots))


def build_plan(
    *,
    narration_lines: list[str],
    clause_title: str,
    shot_duration_s: float = 2.0,
) -> Plan:
    """Compose one single-shot brief per line, refusing an over-long segment.

    The local-preview role's capability check rejects a single render only
    when its duration exceeds ``max_duration_s`` — so the whole pilot
    segment (every scene's shot summed) is checked against that same ceiling
    here, before anything is loaded. Discovering a rejected geometry at plan
    time costs a second; discovering it an hour into a render costs an hour.

    Raises:
        ValueError: the segment's total duration exceeds ``MAX_DURATION_S``.
    """
    briefs = build_scene_briefs(
        clause_title=clause_title,
        narration_lines=narration_lines,
        shot_duration_s=shot_duration_s,
    )
    total = sum(s.duration_s for b in briefs for s in b.shots)
    if total > MAX_DURATION_S:
        raise ValueError(
            f"segment is {total}s but the local-preview role declares "
            f"max_duration_s={MAX_DURATION_S}; it would be refused before rendering"
        )
    return Plan(briefs=briefs, clause_title=clause_title, shot_duration_s=shot_duration_s)


def sha256_bytes(data: bytes) -> str:
    """Hash the rendered bytes — this is what the fidelity attestation names."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def concat(clips: list[Path], out: Path) -> None:
    """Join the per-scene clips with ffmpeg's concat demuxer (no re-encode)."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        for clip in clips:
            fh.write(f"file '{clip.resolve()}'\n")
        listing = fh.name
    subprocess.run(  # noqa: S603 - fixed argv, no shell, no untrusted input
        [  # noqa: S607 - "ffmpeg" is resolved via PATH deliberately, not user input
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            listing,
            "-c",
            "copy",
            str(out),
        ],
        check=True,
        capture_output=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="plan only; no torch")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/tmp/sox-pilot.mp4"),  # noqa: S108 - explicit opt-in default
    )
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=9071)
    parser.add_argument("--resolution", default="320p")
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--shot-duration", type=float, default=2.0)
    parser.add_argument("--threads", type=int, default=4, help="pin to physical cores")
    parser.add_argument("--timeout", type=int, default=7200, help="abort rather than run all night")
    args = parser.parse_args(argv)

    plan = build_plan(
        narration_lines=SCRIPT_LINES,
        clause_title="ICFR awareness",
        shot_duration_s=args.shot_duration,
    )
    print(
        f"[ plan       ] {len(plan.briefs)} scenes, {plan.total_duration_s}s total, "
        f"{args.resolution}, {args.steps} steps, seed {args.seed}"
    )
    for i, brief in enumerate(plan.briefs):
        print(f"  scene {i}: {brief.shots[0].dialogue}")
    if args.dry_run:
        return 0

    # Imported here so --dry-run needs neither torch nor the [local] extra.
    import wegofwd_video as wv

    provider_id, model = wv.resolve_role("local-preview")
    # steps/guidance/timeout/on_progress/threads belong to the PROVIDER, not
    # the request — an earlier revision of this harness got that backwards.
    provider = wv.build_provider(
        provider_id,
        model=model,
        steps=args.steps,
        guidance=1.0,
        timeout=args.timeout,
        on_progress=lambda step, total, elapsed: print(
            f"    step {step}/{total}  {elapsed / step:6.1f} s/step",
            flush=True,
        ),
        threads=args.threads,
    )

    clips: list[Path] = []
    scenes: list[dict[str, Any]] = []
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        for i, brief in enumerate(plan.briefs):
            clip = Path(tmp) / f"scene_{i:02d}.mp4"
            t0 = time.monotonic()
            result = provider.generate(
                wv.VideoRequest(
                    brief=brief,
                    resolution=args.resolution,
                    aspect_ratio="16:9",
                    fps=24,
                    target_duration_s=args.shot_duration,
                    seed=args.seed + i,
                    audio=False,  # local-preview declares native_audio=False
                )
            )
            # The rendered bytes are result.asset_bytes, not result.content —
            # another spot an earlier revision of this harness got backwards.
            if not result.asset_bytes:
                raise RuntimeError(f"scene {i} produced no asset_bytes")
            clip.write_bytes(result.asset_bytes)
            elapsed = time.monotonic() - t0
            print(f"[ scene {i}    ] {elapsed / 60:.1f} min, {len(result.asset_bytes)} bytes")
            clips.append(clip)
            scenes.append(
                {
                    "index": i,
                    "seed": args.seed + i,
                    "wall_clock_s": round(elapsed, 1),
                    "bytes": len(result.asset_bytes),
                    "raw": getattr(result, "raw", {}),
                }
            )
        concat(clips, args.out)

    data = args.out.read_bytes()
    digest = sha256_bytes(data)
    total = time.monotonic() - started
    print(f"[ segment    ] {total / 60:.1f} min total -> {args.out} ({len(data)} bytes)")
    print(f"[ hash       ] {digest}")
    print("  Attest this hash via content_review.attest_draft_video after watching it.")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "clause_title": plan.clause_title,
                    "resolution": args.resolution,
                    "steps": args.steps,
                    "shot_duration_s": args.shot_duration,
                    "total_duration_s": plan.total_duration_s,
                    "wall_clock_s": round(total, 1),
                    "output_bytes": len(data),
                    "video_asset_hash": digest,
                    "scenes": scenes,
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
