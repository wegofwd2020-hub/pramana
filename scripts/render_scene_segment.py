"""Render the full SOX segment with scene prompts — the artifact gate 2 would attest.

Everything before this rendered ONE test scene to isolate a variable. This
renders all five narration lines and concatenates them, because a fidelity
attester does not sign off a frame; they watch a segment and decide whether it
depicts the approved script and depicts nothing misleading.

Settings are the ones human review selected, one at a time:

* **480p and 30 steps** — the two improvements the reviewer picked out
  ("images of both persons look good", "much better") and which `combine_render`
  confirmed compound rather than conflict.
* **guidance 1.0, distilled transformer** — the only combination that renders
  at all. CFG is broken here (wegofwd-video#6) and the repo checkpoint produces
  incoherent output even at its own operating point.
* **Scene prompts, not "a compliance presenter explains: {line}"** — the single
  change that removed the burned-in caption artifact. The templated prompt
  describes stock corporate training footage, a genre that ships with captions;
  the model reproduced the look and, unable to spell, emitted letterform-shaped
  marks. Describing a scene instead removed them entirely.

The prompts deliberately do **not** restate the narration. The footage is B-roll
and asserts no statute — the claims live in the transcript, which gate 1 approves
and which the learner reads (PR #43). A scene should look like its subject, not
illustrate its sentence.

Usage::

    python scripts/render_scene_segment.py --dry-run
    python scripts/render_scene_segment.py --out /workspace/segment/sox-scene.mp4
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from wegofwd_video import Shot, VideoBrief

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.combine_render import SCENE_STYLE
from scripts.render_sox_pilot import SCRIPT_LINES, concat, sha256_bytes
from scripts.render_variants import BASELINE_NEGATIVE, DISTILLED, SCENE_PROMPTS, environment


def build_briefs(*, duration_s: float) -> list[VideoBrief]:
    """One single-shot brief per narration line, using the hand-written scenes.

    Built directly rather than through ``build_video_brief``, whose template
    would prefix "a compliance presenter explains:" onto a scene description and
    reintroduce the exact genre cue these prompts exist to avoid.

    ``dialogue`` still carries the narration line so provenance records which
    line each scene belongs to; the provider drops it (no audio track).
    """
    if len(SCENE_PROMPTS) != len(SCRIPT_LINES):
        raise ValueError(
            f"{len(SCENE_PROMPTS)} scene prompts for {len(SCRIPT_LINES)} narration lines; "
            "they must correspond 1:1 or a scene will illustrate the wrong claim"
        )
    return [
        VideoBrief(
            global_style=SCENE_STYLE,
            global_negative=BASELINE_NEGATIVE,
            shots=(
                Shot(
                    scene_index=i + 1,
                    prompt=prompt,
                    dialogue=line,
                    duration_s=duration_s,
                ),
            ),
        )
        for i, (prompt, line) in enumerate(zip(SCENE_PROMPTS, SCRIPT_LINES, strict=True))
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("segment/sox-scene.mp4"))
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=9071)
    parser.add_argument("--resolution", default="480p")
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--shot-duration", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args(argv)

    briefs = build_briefs(duration_s=args.shot_duration)
    print(
        f"[ plan ] {len(briefs)} scenes x {args.shot_duration}s = "
        f"{len(briefs) * args.shot_duration}s, {args.resolution}, {args.steps} steps, "
        f"guidance 1.0, distilled"
    )
    for i, (brief, line) in enumerate(zip(briefs, SCRIPT_LINES, strict=True)):
        print(f"  scene {i}: {brief.shots[0].prompt[:88]}")
        print(f"           ({line[:80]})")
    if args.dry_run:
        return 0

    env = environment()
    print(f"[ env  ] {json.dumps(env)}")
    if not env.get("cuda_available"):
        print("Refusing to render a full segment on CPU.", file=sys.stderr)
        return 1

    import wegofwd_video as wv

    provider_id, model = wv.resolve_role("local-preview")
    provider = wv.build_provider(
        provider_id,
        model=model,
        steps=args.steps,
        guidance=1.0,
        timeout=args.timeout,
        transformer_file=DISTILLED,
        device="cuda",
        dtype="float32",
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    scenes: list[dict[str, Any]] = []
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        clips: list[Path] = []
        for i, brief in enumerate(briefs):
            t0 = time.monotonic()
            result = provider.generate(
                wv.VideoRequest(
                    brief=brief,
                    resolution=args.resolution,
                    aspect_ratio="16:9",
                    fps=24,
                    target_duration_s=args.shot_duration,
                    seed=args.seed + i,
                    audio=False,
                )
            )
            if not result.asset_bytes:
                raise RuntimeError(f"scene {i} produced no asset_bytes")
            clip = Path(tmp) / f"scene_{i:02d}.mp4"
            clip.write_bytes(result.asset_bytes)
            clips.append(clip)
            elapsed = time.monotonic() - t0
            print(f"  scene {i}: {elapsed:5.1f}s  {len(result.asset_bytes):>9,} B", flush=True)
            scenes.append(
                {
                    "index": i,
                    "seed": args.seed + i,
                    "prompt": brief.shots[0].prompt,
                    "narration": SCRIPT_LINES[i],
                    "wall_clock_s": round(elapsed, 1),
                    "bytes": len(result.asset_bytes),
                    "raw": getattr(result, "raw", {}) or {},
                }
            )
        concat(clips, args.out)

    data = args.out.read_bytes()
    digest = sha256_bytes(data)
    total = time.monotonic() - started
    print(f"\n[ segment ] {total / 60:.1f} min -> {args.out} ({len(data):,} B)")
    print(f"[ hash    ] {digest}")

    out_json = args.json or args.out.with_suffix(".json")
    out_json.write_text(
        json.dumps(
            {
                "environment": env,
                "resolution": args.resolution,
                "steps": args.steps,
                "guidance": 1.0,
                "transformer_file": DISTILLED,
                "style": SCENE_STYLE,
                "negative": BASELINE_NEGATIVE,
                "seed": args.seed,
                "shot_duration_s": args.shot_duration,
                "total_duration_s": len(briefs) * args.shot_duration,
                "wall_clock_s": round(total, 1),
                "output_bytes": len(data),
                "video_asset_hash": digest,
                "scenes": scenes,
            },
            indent=2,
        )
    )
    print(f"[ results ] {out_json}")
    print("\nThis is a gate-2 candidate, NOT an attestation. A human watches it and")
    print("decides whether it depicts the approved script and nothing misleading.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
