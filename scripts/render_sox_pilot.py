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
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pramana.domain.video_generation import build_scene_briefs

#: The local-preview role's ceiling on a single scene's render duration — the
#: provider's own rule, checked directly per scene in ``build_plan``. The
#: same number is also reused, deliberately, as this harness's budget for the
#: whole pilot segment's total duration; that reuse is a cost-guard choice,
#: not something the provider itself enforces.
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
    """Compose one single-shot brief per line, enforcing two separate limits.

    Each brief is one render, so the local-preview role's own capability check
    — which rejects a single render's ``duration_s`` only when it exceeds
    ``max_duration_s`` — is checked here directly, per scene, rather than left
    to fall out of the segment arithmetic below.

    Separately, this harness costs the *whole pilot segment* against that
    same ceiling as a deliberate, reused budget: it is not a rule the provider
    itself enforces (the provider never sees the segment, only one render at a
    time), but it keeps the pilot short and catches a runaway line count or
    per-line duration before anything loads.

    Discovering either kind of rejection at plan time costs a second;
    discovering it an hour into a render costs an hour.

    Raises:
        ValueError: a single scene's render would exceed ``MAX_DURATION_S``
            (the provider's own rule), or the segment's total duration
            exceeds the harness's budget (derived from that same ceiling).
    """
    briefs = build_scene_briefs(
        clause_title=clause_title,
        narration_lines=narration_lines,
        shot_duration_s=shot_duration_s,
    )

    # The provider's real rule, checked explicitly rather than left to fall out
    # of the segment arithmetic below. Each brief is one render, so a shot
    # longer than the ceiling is a render the capability check will refuse
    # outright — independent of how many other scenes exist.
    for i, brief in enumerate(briefs):
        render_s = sum(s.duration_s for s in brief.shots)
        if render_s > MAX_DURATION_S:
            raise ValueError(
                f"scene {i} is {render_s}s, over the local-preview role's "
                f"max_duration_s={MAX_DURATION_S}; the provider would refuse this render"
            )

    # The harness's own cost guard: a budget on the concatenated segment,
    # deliberately reusing the provider's per-render ceiling as its value.
    # This is NOT a rule the provider enforces (it never sees the segment),
    # so the message must not claim rejection — only that this pilot's cost
    # budget is exceeded.
    total = sum(s.duration_s for b in briefs for s in b.shots)
    if total > MAX_DURATION_S:
        raise ValueError(
            f"segment totals {total}s, over the {MAX_DURATION_S}s budget this pilot "
            f"was costed against. The provider's own max_duration_s applies per render, "
            f"not per segment — this is the harness's cost guard, deliberately reusing "
            f"the same ceiling."
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
    try:
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
    finally:
        os.unlink(listing)


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

    # Resolve the role BEFORE the dry-run early return. Validating geometry while
    # the provider is absent is how this script once reported a healthy plan and
    # then died six minutes later at resolve_role.
    try:
        import wegofwd_video as wv

        provider_id, model = wv.resolve_role("local-preview")
    except ImportError as exc:  # pragma: no cover - depends on the render extra
        raise SystemExit(
            "wegofwd_video is not importable; install the render extra: pip install -e '.[render]'"
        ) from exc
    print(f"[ role       ] local-preview -> {provider_id} / {model}")
    if args.dry_run:
        return 0

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
