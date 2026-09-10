"""Render the SOX pilot segment three ways, to find out what the quality ceiling is.

The pilot's first render was refused at gate 2 (``docs/sox-video-pilot-run.md``):
the imagery depicted nothing specific and carried hallucinated on-screen text.
There are two candidate explanations and the pilot run cannot separate them,
because it varied neither:

1. **Render settings.** It ran ``guidance=1.0``, which means classifier-free
   guidance is OFF. Nothing pushes the sample toward the prompt, so it drifts to
   the model's prior — and, crucially, the negative prompt is inert, since a
   negative only has force through CFG. ``"no on-screen text artifacts"`` never
   suppressed anything. It also ran 8 steps at 576x320 on the *distilled* 2B
   transformer, which is the fast end of every one of those dials.

2. **The prompt.** ``build_video_brief`` emits one templated line per scene —
   ``f"a compliance presenter explains: {line}"`` — plus a fixed style and a
   fixed shot_type/camera_move/lighting triple. That is the entire visual
   instruction. A narration line like "a missing owner is itself a finding"
   gives a diffusion model nothing to draw.

This harness renders a **ladder**, so each rung isolates one of them:

    baseline  -> exactly the refused settings; the control
    quality   -> same prompts, better render settings
    prompted  -> quality's settings, hand-written per-scene prompts

``baseline -> quality`` attributes the difference to render settings.
``quality -> prompted`` attributes it to the prompt. Running only the third
would tell you the ceiling is reachable but not which dial got you there, and
the two have very different costs to fix.

Needs a GPU. ``quality`` and ``prompted`` are ~8x the baseline's stepping cost
(2.25x the latent tokens, 3.75x the steps), and the baseline already took 98
minutes on the CPU box. Provision with ``scripts/runpod_setup.sh``.

Usage::

    python scripts/render_variants.py --dry-run
    python scripts/render_variants.py --out-dir /workspace/variants
    python scripts/render_variants.py --variants baseline,prompted
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wegofwd_video import Shot, VideoBrief

# `scripts` is a package, so the sibling import below needs the repo root on the
# path. Running this file directly ("python scripts/render_variants.py", the way
# render_sox_pilot.py is documented) puts scripts/ there instead, not the root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pramana.domain.video_generation import build_scene_briefs
from scripts.render_sox_pilot import SCRIPT_LINES, concat, sha256_bytes

#: The five narration lines are shared with the pilot harness, not copied — the
#: whole comparison is meaningless if the two renders describe different content.

#: Hand-written visual prompts for the `prompted` variant, one per SCRIPT_LINES
#: entry and in the same order.
#:
#: These describe *what is on screen*, which the templated prompt never did.
#: Note what they are NOT: they do not restate the narration. The footage is
#: B-roll and asserts no statute — the claims live in the transcript, which is
#: what gate 1 approves and what the learner actually reads. So a scene needs to
#: look like its subject, not illustrate its sentence.
SCENE_PROMPTS: tuple[str, ...] = (
    "A single sheet of paper on a desk, a signature line at its foot, a pen "
    "resting beside it. Shallow depth of field, the far edge of the desk soft",
    "A hand places a dated stamp onto an open ledger, the page half filled with "
    "ruled rows. Close on the hands, the ledger flat and evenly lit",
    "A wide, quiet meeting room seen from the doorway, one bound folder squared "
    "at the head of an empty table. Cool daylight from tall windows",
    "One empty chair at a long table of occupied chairs, seen straight on. The "
    "empty seat centred and slightly brighter than the rest",
    "A slow drift across a tidy, empty office at dusk, desks in order, monitors "
    "dark. Warm low light from the windows",
)

#: LTX's T5 encoder truncates at this many tokens; anything past it is silently
#: dropped. Imported rather than restated so a provider change cannot desync it.
try:
    from wegofwd_video.providers.local_diffusion import PROMPT_MAX_TOKENS
except ImportError:  # pragma: no cover - only when the local extra is absent
    PROMPT_MAX_TOKENS = 128

#: The style line the pilot used, restated here so the baseline is exactly
#: reproducible from this file alone. "flat illustration" is very likely the
#: source of the "highly cartoonish" quality the reviewer described — that is
#: the requested aesthetic, not a defect, but it is a house-style decision that
#: deserves to be made deliberately rather than inherited.
BASELINE_STYLE = "clean corporate explainer, flat illustration, neutral palette"

#: The prompt template the refused render actually used, pinned here as a
#: literal rather than inherited from ``build_video_brief``.
#:
#: The domain default has since changed — that template is what summoned the
#: captioned stock footage, and it was replaced. But this file's job is to
#: reproduce the configuration a reviewer refused, so it has to carry the old
#: wording itself. Inheriting it would mean the "baseline" quietly tracks the
#: current default and stops being a baseline at all.
BASELINE_PROMPT_TEMPLATE = "a compliance presenter explains: {line}"
BASELINE_NEGATIVE = "no on-screen text artifacts, no logos, no real faces, no flashing"

#: The style for the two improved variants. Photographic rather than
#: illustrated, and the negative is stated in the terms a diffusion model
#: actually responds to (things depicted, not instructions) — "no on-screen
#: text artifacts" reads to the model as a request for text.
QUALITY_STYLE = (
    "restrained corporate documentary photography, muted neutral palette, "
    "natural light, shallow depth of field, no people's faces in frame"
)
QUALITY_NEGATIVE = (
    "text, letters, words, captions, watermark, logo, signage, subtitles, "
    "human face, distorted hands, oversaturated, flashing, cartoon, illustration"
)


@dataclass(frozen=True)
class Variant:
    """One rung of the ladder: a full render configuration with a rationale."""

    name: str
    why: str
    resolution: str
    steps: int
    guidance: float
    #: None means "use the pipeline repo's own transformer" — LTX-Video-0.9.5's
    #: bundled 2B, which is NOT distilled. That matters: distilled checkpoints
    #: are *trained* for guidance 1.0, and raising guidance on one usually
    #: degrades the output rather than improving it. So "turn CFG on" and "stop
    #: using the distilled transformer" are the same change, not two.
    transformer_file: str | None
    style: str
    negative: str
    #: Hand-written prompts, or None to use build_scene_briefs' templated one.
    scene_prompts: tuple[str, ...] | None = None
    shot_type: str = "medium"
    camera_move: str = "static"
    lighting: str = "even office light"

    @property
    def is_distilled(self) -> bool:
        return self.transformer_file is not None


DISTILLED = "ltxv-2b-0.9.8-distilled.safetensors"

VARIANTS: tuple[Variant, ...] = (
    Variant(
        name="baseline",
        why=(
            "The control: byte-for-byte the configuration gate 2 refused. "
            "Without it the other two prove nothing, because there is no "
            "same-hardware reference to compare against — the pilot's own "
            "render was on a CPU and cannot serve as one."
        ),
        resolution="320p",
        steps=8,
        guidance=1.0,
        transformer_file=DISTILLED,
        style=BASELINE_STYLE,
        negative=BASELINE_NEGATIVE,
    ),
    Variant(
        name="quality",
        why=(
            "Render settings only — same templated prompts as baseline. "
            "CFG on at 3.0 (which also makes the negative prompt effective for "
            "the first time), 30 steps, 480p, non-distilled transformer. "
            "A difference here is attributable to settings alone."
        ),
        resolution="480p",
        steps=30,
        guidance=3.0,
        transformer_file=None,
        style=QUALITY_STYLE,
        negative=QUALITY_NEGATIVE,
    ),
    Variant(
        name="prompted",
        why=(
            "Quality's render settings, plus hand-written per-scene prompts. "
            "The delta from `quality` is the prompt's contribution alone — and "
            "it is the cheap fix if it turns out to dominate, because it needs "
            "no GPU in production, only a better build_video_brief."
        ),
        resolution="480p",
        steps=30,
        guidance=3.0,
        transformer_file=None,
        style=QUALITY_STYLE,
        negative=QUALITY_NEGATIVE,
        scene_prompts=SCENE_PROMPTS,
        shot_type="",
        camera_move="",
        lighting="",
    ),
)


@dataclass
class SceneRecord:
    index: int
    seed: int
    prompt_words: int
    wall_clock_s: float = 0.0
    bytes_out: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


def build_briefs(variant: Variant, *, shot_duration_s: float) -> list[VideoBrief]:
    """One single-shot brief per narration line, templated or hand-written.

    The local provider joins a multi-shot brief into ONE clip and sums the
    durations, so distinct scenes require one brief each — the same reason
    ``build_scene_briefs`` exists.
    """
    if variant.scene_prompts is None:
        return build_scene_briefs(
            clause_title="ICFR awareness",
            narration_lines=SCRIPT_LINES,
            scene_prompts=[BASELINE_PROMPT_TEMPLATE.format(line=line) for line in SCRIPT_LINES],
            shot_duration_s=shot_duration_s,
            style=variant.style,
            negative=variant.negative,
        )

    if len(variant.scene_prompts) != len(SCRIPT_LINES):
        raise ValueError(
            f"variant {variant.name!r} has {len(variant.scene_prompts)} hand-written "
            f"prompts for {len(SCRIPT_LINES)} narration lines; they must correspond "
            f"1:1 or the comparison against the other variants is not like-for-like"
        )

    # Built directly rather than through build_video_brief, whose template would
    # prefix "a compliance presenter explains:" onto a visual description and
    # produce nonsense. dialogue still carries the narration line so the
    # provenance records which line each scene belongs to; the local provider
    # drops dialogue from the prompt (there is no audio track).
    return [
        VideoBrief(
            global_style=variant.style,
            global_negative=variant.negative,
            shots=(
                Shot(
                    scene_index=i + 1,
                    prompt=prompt,
                    shot_type=variant.shot_type,
                    camera_move=variant.camera_move,
                    lighting=variant.lighting,
                    dialogue=line,
                    duration_s=shot_duration_s,
                ),
            ),
        )
        for i, (prompt, line) in enumerate(zip(variant.scene_prompts, SCRIPT_LINES, strict=True))
    ]


def check_prompt_length(briefs: list[VideoBrief], variant: Variant) -> list[int]:
    """Warn on prompts the T5 encoder will silently truncate.

    Word count is an approximation of the token count — the real one needs the
    T5 tokenizer, which needs the weights loaded, which is exactly what we are
    trying to check *before*. English prose runs roughly 1.3 tokens per word, so
    the threshold is deliberately conservative. A truncated prompt is a
    particularly nasty failure because it looks like a normal render.
    """
    from wegofwd_video.providers.local_diffusion import render_prompt

    counts = []
    budget_words = int(PROMPT_MAX_TOKENS / 1.3)
    for i, brief in enumerate(briefs):
        words = len(render_prompt(brief).split())
        counts.append(words)
        if words > budget_words:
            print(
                f"  ! scene {i} prompt is ~{words} words, over the ~{budget_words}-word "
                f"budget for T5's {PROMPT_MAX_TOKENS}-token limit; the tail will be "
                f"silently dropped ({variant.name})",
                file=sys.stderr,
            )
    return counts


def environment() -> dict[str, Any]:
    """Everything a later reader needs to know this render cannot be reproduced.

    Determinism in this provider is per (seed, torch build, device). The pilot
    spec leans on it as a compliance property — an approved SOX version must be
    regenerable — so if any of this footage is ever attested, this block is the
    provenance that says on what.
    """
    env: dict[str, Any] = {"python": platform.python_version(), "platform": platform.platform()}
    try:
        import torch

        env["torch"] = torch.__version__
        env["cuda"] = torch.version.cuda
        env["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            env["gpu"] = torch.cuda.get_device_name(0)
            env["gpu_memory_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / 1024**3, 1
            )
    except ImportError:
        env["torch"] = None
    try:
        import transformers

        env["transformers"] = transformers.__version__
    except ImportError:
        env["transformers"] = None
    return env


def render_variant(
    variant: Variant,
    *,
    out_dir: Path,
    seed: int,
    shot_duration_s: float,
    device: str,
    dtype: str,
    timeout: int,
) -> dict[str, Any]:
    """Render one variant's five scenes and concatenate them. Returns its record."""
    import wegofwd_video as wv

    provider_id, model = wv.resolve_role("local-preview")
    briefs = build_briefs(variant, shot_duration_s=shot_duration_s)
    prompt_words = check_prompt_length(briefs, variant)

    provider = wv.build_provider(
        provider_id,
        model=model,
        steps=variant.steps,
        guidance=variant.guidance,
        timeout=timeout,
        transformer_file=variant.transformer_file,
        device=device,
        dtype=dtype,
        on_progress=lambda step, total, elapsed: print(
            f"      step {step}/{total}  {elapsed / step:6.1f} s/step", flush=True
        ),
    )

    scene_dir = out_dir / variant.name
    scene_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    scenes: list[SceneRecord] = []
    started = time.monotonic()

    for i, brief in enumerate(briefs):
        clip = scene_dir / f"scene_{i:02d}.mp4"
        # Same seed per scene index across variants — the whole comparison rests
        # on the noise being identical, so only the configuration differs.
        scene_seed = seed + i
        t0 = time.monotonic()
        result = provider.generate(
            wv.VideoRequest(
                brief=brief,
                resolution=variant.resolution,
                aspect_ratio="16:9",
                fps=24,
                target_duration_s=shot_duration_s,
                seed=scene_seed,
                audio=False,  # local-preview declares native_audio=False
            )
        )
        if not result.asset_bytes:
            raise RuntimeError(f"{variant.name} scene {i} produced no asset_bytes")
        clip.write_bytes(result.asset_bytes)
        elapsed = time.monotonic() - t0
        print(
            f"    scene {i}: {elapsed / 60:5.1f} min  {len(result.asset_bytes):>9,} bytes",
            flush=True,
        )
        clips.append(clip)
        scenes.append(
            SceneRecord(
                index=i,
                seed=scene_seed,
                prompt_words=prompt_words[i],
                wall_clock_s=round(elapsed, 1),
                bytes_out=len(result.asset_bytes),
                raw=getattr(result, "raw", {}) or {},
            )
        )

    segment = out_dir / f"{variant.name}.mp4"
    concat(clips, segment)
    data = segment.read_bytes()
    total = time.monotonic() - started
    digest = sha256_bytes(data)
    print(f"  -> {segment}  {total / 60:.1f} min  {len(data):,} bytes")
    print(f"     {digest}")

    return {
        "variant": variant.name,
        "why": variant.why,
        "resolution": variant.resolution,
        "steps": variant.steps,
        "guidance": variant.guidance,
        "distilled": variant.is_distilled,
        "transformer_file": variant.transformer_file,
        "style": variant.style,
        "negative": variant.negative,
        "hand_written_prompts": variant.scene_prompts is not None,
        "output": str(segment),
        "output_bytes": len(data),
        "video_asset_hash": digest,
        "wall_clock_s": round(total, 1),
        "scenes": [vars(s) for s in scenes],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="compose and check; no render")
    parser.add_argument("--out-dir", type=Path, default=Path("variants"))
    parser.add_argument("--json", type=Path, default=None, help="default: <out-dir>/results.json")
    parser.add_argument("--seed", type=int, default=9071, help="same as the pilot render")
    parser.add_argument("--shot-duration", type=float, default=2.0)
    parser.add_argument(
        "--variants", default="", help="comma-separated subset; default is all three, in order"
    )
    parser.add_argument("--device", default="auto", help="cuda | cpu | auto")
    parser.add_argument("--dtype", default="bfloat16", help="transformer dtype")
    parser.add_argument("--timeout", type=int, default=7200, help="per render, seconds")
    args = parser.parse_args(argv)

    selected = VARIANTS
    if args.variants:
        wanted = [n.strip() for n in args.variants.split(",") if n.strip()]
        known = {v.name: v for v in VARIANTS}
        unknown = [n for n in wanted if n not in known]
        if unknown:
            parser.error(f"unknown variant(s) {unknown}; known: {sorted(known)}")
        selected = tuple(known[n] for n in wanted)

    env = environment()
    device = args.device
    if device == "auto":
        device = "cuda" if env.get("cuda_available") else "cpu"

    print(f"[ env        ] {json.dumps(env)}")
    print(f"[ device     ] {device} / {args.dtype}")
    if device == "cpu":
        print(
            "  ! CPU: the two improved variants are ~8x the baseline's stepping cost,\n"
            "    and the baseline itself took 98 minutes on the pilot box. Use a GPU\n"
            "    (scripts/runpod_setup.sh) or select --variants baseline.",
            file=sys.stderr,
        )

    # Compose and length-check everything BEFORE loading a single weight. A
    # prompt problem found now costs a second; found three renders in, it costs
    # however long those renders took.
    for variant in selected:
        briefs = build_briefs(variant, shot_duration_s=args.shot_duration)
        print(
            f"\n[ {variant.name:<10}] {variant.resolution}, {variant.steps} steps, "
            f"guidance {variant.guidance}, "
            f"{'distilled 2B' if variant.is_distilled else 'repo 2B (not distilled)'}"
        )
        print(f"             {variant.why}")
        words = check_prompt_length(briefs, variant)
        for i, brief in enumerate(briefs):
            print(f"    scene {i} (~{words[i]:>3} words): {brief.shots[0].prompt[:78]}")

    if args.dry_run:
        return 0

    # Auto-detected CPU is almost always an accident — a pod whose torch has no
    # CUDA, or the wrong box entirely. Refuse rather than start a render that
    # will not finish this week. An explicit --device cpu is a decision, so it
    # proceeds.
    if device != "cuda" and args.device == "auto":
        print(
            "\nRefusing to auto-run on CPU: these variants will not finish in reasonable\n"
            "time. Provision a GPU (scripts/runpod_setup.sh), or pass --device cpu to\n"
            "override — ideally with --variants baseline.",
            file=sys.stderr,
        )
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for variant in selected:
        print(f"\n=== {variant.name} ===", flush=True)
        results.append(
            render_variant(
                variant,
                out_dir=args.out_dir,
                seed=args.seed,
                shot_duration_s=args.shot_duration,
                device=device,
                dtype=args.dtype,
                timeout=args.timeout,
            )
        )

    out_json = args.json or (args.out_dir / "results.json")
    out_json.write_text(
        json.dumps(
            {
                "environment": env,
                "device": device,
                "dtype": args.dtype,
                "seed": args.seed,
                "shot_duration_s": args.shot_duration,
                "narration_lines": SCRIPT_LINES,
                "variants": results,
            },
            indent=2,
        )
    )

    print(f"\n[ results    ] {out_json}")
    print("\nWatch them in ladder order and answer two questions:")
    print("  baseline -> quality   did the render settings fix it?")
    print("  quality  -> prompted  did the prompt fix it?")
    print("\nNeither of these is attested. If any variant is ever published, its")
    print("environment block above is the provenance — these frames are NOT")
    print("reproducible on the CPU box, or on a different GPU.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
