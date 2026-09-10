"""Combine the two improvements that worked, and test whether prompt alone kills the captions.

Human review of a bisect harness's output (commit ``1d1df12``, since removed)
established, at guidance 1.0 on the distilled checkpoint:

* **30 steps** (320p) — "images of both persons look good"; the best of the set
* **480p** (8 steps) — "much better, but there seems to be background images
  which is distorting"

480p has 2.25x the latent tokens but the same 8 steps, so there is not enough
denoising to resolve the extra detail and the background falls apart while the
subject improves. **Nobody has run 480p AND 30 steps** — the bisect changes one
variable at a time from a control, so it structurally never reaches that cell.
That is this harness's first job.

Its second job is the on-screen text. Extracted frames show it is not background
texture but **burned-in subtitles** — three centred lines exactly where captions
sit. ``build_video_brief`` prompts every scene as
``f"a compliance presenter explains: {line}"``, which describes *stock corporate
training footage*, and that genre ships with captions burned in. The model
reproduces the look and, unable to spell, emits letterform-shaped marks.

If that is right, rewriting the prompt removes the captions **without** needing
classifier-free guidance — which matters, because CFG is broken on this
checkpoint (wegofwd-video#6) and the negative prompt is therefore inert. The
`scene` run tests exactly that: same settings, a prompt that describes a scene
rather than a presenter explaining something.

Usage::

    python scripts/combine_render.py --dry-run
    python scripts/combine_render.py --out-dir /workspace/combine
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wegofwd_video import Shot, VideoBrief

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pramana.domain.video_generation import build_scene_briefs
from scripts.render_sox_pilot import SCRIPT_LINES, sha256_bytes
from scripts.render_variants import BASELINE_NEGATIVE, BASELINE_STYLE, DISTILLED, environment

#: Same narration line the bisect harness used, so results stay comparable
#: across harnesses. (It was defined there too; that harness has since been
#: removed, so this is now the only copy.)
LINE_INDEX = 2

#: A prompt for the same narration line that describes **what is on screen**
#: rather than "a presenter explains". Deliberately concrete and deliberately
#: not a talking head: the genre cue is what drags in captioned stock footage,
#: and a presenter delivering a line to camera is that genre's defining shot.
#:
#: It also does not restate the narration. The footage is B-roll and asserts no
#: statute — the claims live in the transcript, which gate 1 approves and which
#: the learner now actually reads (PR #43). A scene needs to look like its
#: subject, not illustrate its sentence.
SCENE_PROMPT = (
    "A bound audit folder lies closed on a boardroom table, a numbered tab "
    "protruding from its edge. Late afternoon light from a window, shallow "
    "depth of field, the far end of the table soft"
)

#: The house style, minus "flat illustration" — that phrase is very likely the
#: source of the "highly cartoonish" quality the first review flagged, and it is
#: a deliberate aesthetic choice rather than a defect, so it is worth varying.
SCENE_STYLE = (
    "restrained corporate documentary photography, muted neutral palette, "
    "natural window light, shallow depth of field"
)


@dataclass(frozen=True)
class Run:
    name: str
    why: str
    resolution: str = "480p"
    steps: int = 30
    guidance: float = 1.0
    transformer_file: str | None = DISTILLED
    #: None -> the templated prompt from build_video_brief.
    scene_prompt: str | None = None
    style: str = BASELINE_STYLE


RUNS: tuple[Run, ...] = (
    Run(
        "combined",
        "480p AND 30 steps, current prompt — do the two improvements compound?",
    ),
    Run(
        "scene",
        "480p, 30 steps, prompt describes a SCENE not a presenter — "
        "do the captions go away without CFG?",
        scene_prompt=SCENE_PROMPT,
        style=SCENE_STYLE,
    ),
    Run(
        "repo_fair",
        "repo (non-distilled) transformer at its OWN operating point (30 steps) "
        "— the fair test wegofwd-video#6 still needs",
        transformer_file=None,
    ),
)


def build_brief(run: Run, *, duration_s: float) -> VideoBrief:
    """Templated brief, or a hand-written single-shot one."""
    if run.scene_prompt is None:
        return build_scene_briefs(
            clause_title="ICFR awareness",
            narration_lines=[SCRIPT_LINES[LINE_INDEX]],
            shot_duration_s=duration_s,
            style=run.style,
            negative=BASELINE_NEGATIVE,
        )[0]
    # Built directly: build_video_brief would prefix "a compliance presenter
    # explains:" onto a scene description, reintroducing the exact genre cue
    # this run exists to remove.
    return VideoBrief(
        global_style=run.style,
        global_negative=BASELINE_NEGATIVE,
        shots=(
            Shot(
                scene_index=1,
                prompt=run.scene_prompt,
                dialogue=SCRIPT_LINES[LINE_INDEX],
                duration_s=duration_s,
            ),
        ),
    )


def render_one(
    run: Run, *, out_dir: Path, seed: int, duration_s: float, timeout: int
) -> dict[str, Any]:
    import wegofwd_video as wv

    provider_id, model = wv.resolve_role("local-preview")
    brief = build_brief(run, duration_s=duration_s)
    provider = wv.build_provider(
        provider_id,
        model=model,
        steps=run.steps,
        guidance=run.guidance,
        timeout=timeout,
        transformer_file=run.transformer_file,
        device="cuda",
        dtype="float32",
    )
    t0 = time.monotonic()
    result = provider.generate(
        wv.VideoRequest(
            brief=brief,
            resolution=run.resolution,
            aspect_ratio="16:9",
            fps=24,
            target_duration_s=duration_s,
            seed=seed,
            audio=False,
        )
    )
    if not result.asset_bytes:
        raise RuntimeError(f"{run.name} produced no asset_bytes")
    elapsed = time.monotonic() - t0
    path = out_dir / f"{run.name}.mp4"
    path.write_bytes(result.asset_bytes)
    print(f"  {run.name:10} {elapsed:5.1f}s  {len(result.asset_bytes):>9,} B", flush=True)
    return {
        "run": run.name,
        "why": run.why,
        "resolution": run.resolution,
        "steps": run.steps,
        "guidance": run.guidance,
        "transformer_file": run.transformer_file,
        "prompt": brief.shots[0].prompt,
        "style": run.style,
        "output": str(path),
        "output_bytes": len(result.asset_bytes),
        "video_asset_hash": sha256_bytes(result.asset_bytes),
        "wall_clock_s": round(elapsed, 1),
        "raw": getattr(result, "raw", {}) or {},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=Path("combine"))
    parser.add_argument("--seed", type=int, default=9071)
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--runs", default="")
    args = parser.parse_args(argv)

    selected = RUNS
    if args.runs:
        want = [n.strip() for n in args.runs.split(",") if n.strip()]
        known = {r.name: r for r in RUNS}
        bad = [n for n in want if n not in known]
        if bad:
            parser.error(f"unknown run(s) {bad}; known: {sorted(known)}")
        selected = tuple(known[n] for n in want)

    print(f"[ line  ] {SCRIPT_LINES[LINE_INDEX]!r}")
    for r in selected:
        brief = build_brief(r, duration_s=args.duration)
        print(
            f"\n[ {r.name:9}] {r.resolution} steps={r.steps} g={r.guidance} "
            f"transformer={r.transformer_file or 'repo'}"
        )
        print(f"            {r.why}")
        print(f"            prompt: {brief.shots[0].prompt[:96]}")
    if args.dry_run:
        return 0

    env = environment()
    print(f"\n[ env   ] {json.dumps(env)}")
    if not env.get("cuda_available"):
        print("Refusing to render on CPU.", file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results = [
        render_one(
            r, out_dir=args.out_dir, seed=args.seed, duration_s=args.duration, timeout=args.timeout
        )
        for r in selected
    ]
    out = args.out_dir / "combine.json"
    out.write_text(
        json.dumps(
            {
                "environment": env,
                "seed": args.seed,
                "line": SCRIPT_LINES[LINE_INDEX],
                "runs": results,
            },
            indent=2,
        )
    )
    print(f"\n[ results ] {out}")
    print("\nJudge these from extracted FRAMES, never from byte size — reading")
    print("sizes alone is what produced a wrong upstream bug report last round.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
