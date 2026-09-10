#!/usr/bin/env bash
#
# Provision a rented GPU pod to render the SOX pilot variants.
#
# Written for RunPod (a PyTorch template pod with a network volume mounted at
# /workspace), but nothing here is RunPod-specific beyond that default path —
# Vast.ai or any CUDA box with a persistent directory works the same way.
#
# The point of the network volume is the weights. The HuggingFace cache for
# LTX-Video is ~26 GB (21 GB for the 0.9.5 diffusers-layout repo, ~6 GB for the
# distilled single-file transformer). Downloading that on every pod start costs
# more wall-clock than the renders do, so HF_HOME lives on the volume and the
# venv sits beside it.
#
# Usage:
#   export WORKSPACE=/workspace          # must be the PERSISTENT volume
#   bash scripts/runpod_setup.sh
#   source "$WORKSPACE/venv/bin/activate"
#   python scripts/render_variants.py --dry-run
#
# Re-running is safe and cheap: every step is skipped when already satisfied.

set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
VENV="$WORKSPACE/venv"
export HF_HOME="${HF_HOME:-$WORKSPACE/hf-cache}"
PRAMANA_DIR="${PRAMANA_DIR:-$WORKSPACE/pramana}"
PRAMANA_REPO="${PRAMANA_REPO:-https://github.com/wegofwd2020-hub/pramana.git}"
WEGOFWD_VIDEO_REF="${WEGOFWD_VIDEO_REF:-v1.1.0}"

say() { printf '\n\033[1m[ %s ]\033[0m %s\n' "$1" "${2:-}"; }

# ---------------------------------------------------------------------------
# 1. Guards. Fail here rather than 20 GB into a download.
# ---------------------------------------------------------------------------
say guards

if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "FATAL: no nvidia-smi. This script is for a GPU pod; on CPU use" >&2
    echo "       scripts/render_sox_pilot.py instead." >&2
    exit 1
fi
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

# The persistent volume is the whole reason for this layout. If WORKSPACE is
# just container-local disk, the 26 GB download dies with the pod and the next
# session pays for it again — silently, and only visible as a slow start.
if ! mountpoint -q "$WORKSPACE" 2>/dev/null; then
    echo "WARNING: $WORKSPACE is not a mount point." >&2
    echo "         If it is not a network volume, the weight cache will NOT" >&2
    echo "         survive this pod and you will re-download ~26 GB next time." >&2
    echo "         Continuing in 10s; Ctrl-C to fix the mount first." >&2
    sleep 10
fi

df -h "$WORKSPACE" | tail -1
avail_gb=$(df -BG --output=avail "$WORKSPACE" | tail -1 | tr -dc '0-9')
if [ "$avail_gb" -lt 40 ]; then
    echo "FATAL: only ${avail_gb} GB free on $WORKSPACE; the weights need ~26 GB" >&2
    echo "       plus room for the venv and the rendered clips. Use >= 50 GB." >&2
    exit 1
fi

mkdir -p "$HF_HOME"

# ---------------------------------------------------------------------------
# 2. Virtualenv on the volume, so it persists with the cache.
# ---------------------------------------------------------------------------
say venv "$VENV"

if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --quiet --upgrade pip

# ---------------------------------------------------------------------------
# 3. torch — CUDA build.
#
# Deliberately NOT pinned to pramana's `[render]` extra (torch==2.14.0). That
# pin exists to reproduce a CPU render byte-for-byte, and it resolves to the
# CPU wheel index. On rented hardware the byte-for-byte claim is already gone
# (see the determinism note at the bottom of this script), so the priority
# here is a torch that matches the pod's CUDA driver.
#
# RunPod PyTorch templates ship one already. Prefer it; only install if absent.
# ---------------------------------------------------------------------------
say torch

if python -c 'import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)' 2>/dev/null; then
    python -c 'import torch; print(f"  present: torch {torch.__version__}, cuda {torch.version.cuda}")'
else
    echo "  no CUDA-enabled torch found; installing"
    # Override with e.g. TORCH_INDEX=https://download.pytorch.org/whl/cu126 if
    # the pod's driver needs a different CUDA series. The default index serves
    # the current stable CUDA build.
    TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu124}"
    python -m pip install torch torchvision --index-url "$TORCH_INDEX"
    python -c 'import torch; assert torch.cuda.is_available(), "torch installed but CUDA still unavailable"'
    python -c 'import torch; print(f"  installed: torch {torch.__version__}, cuda {torch.version.cuda}")'
fi

# ---------------------------------------------------------------------------
# 4. wegofwd-video with its [local] extra (diffusers, transformers, etc).
#
# Installed directly rather than via pramana's `[render]` extra, which would
# drag in the torch==2.14.0 CPU pin and fight step 3. The harness only needs
# two pramana modules, and both are import-light (stdlib + wegofwd_video), so
# pramana goes on sys.path as source instead of being pip-installed.
# ---------------------------------------------------------------------------
say wegofwd-video "$WEGOFWD_VIDEO_REF"

if ! python -c 'import wegofwd_video' 2>/dev/null; then
    python -m pip install \
        "wegofwd-video[local] @ git+https://github.com/wegofwd2020-hub/wegofwd-video@${WEGOFWD_VIDEO_REF}"
fi
python -c 'import wegofwd_video as wv; print("  role:", wv.resolve_role("local-preview"))'

# protobuf is not optional: T5 ships only spiece.model, and transformers
# converts it through SentencePieceExtractor, which imports protobuf. Without
# it the conversion falls back to a TikToken reader and dies asking for
# `tiktoken` — the wrong package, and a genuinely confusing error.
python -c 'import google.protobuf' 2>/dev/null || python -m pip install 'protobuf>=4'

# ---------------------------------------------------------------------------
# 5. pramana source (not installed — only needs to be importable).
# ---------------------------------------------------------------------------
say pramana "$PRAMANA_DIR"

if [ ! -d "$PRAMANA_DIR/.git" ]; then
    git clone --depth 1 "$PRAMANA_REPO" "$PRAMANA_DIR"
else
    git -C "$PRAMANA_DIR" pull --ff-only
fi
PYTHONPATH="$PRAMANA_DIR" python -c \
    'from pramana.domain.video_generation import build_scene_briefs; print("  import ok")'

# ---------------------------------------------------------------------------
# 6. Prefetch the weights, as an explicit step.
#
# This is ~26 GB. Doing it here means the download is a visible line item you
# can watch and retry, rather than a surprise inside the first render — where
# a transport failure is much harder to tell apart from a render failure.
# ---------------------------------------------------------------------------
say weights "$HF_HOME"

# HF rate-limits anonymous downloads per source IP, and RunPod hosts share
# egress addresses — so a pod can land already throttled by other tenants,
# with nothing you did. Observed 2026-09-10: five attempts over five minutes
# all returned 429 on a fresh pod, while the same request from a home
# connection returned 200. Set HF_TOKEN (read scope is enough) to lift it;
# authenticated limits are far higher and follow the account, not the IP.
if [ -n "${HF_TOKEN:-}" ]; then
    echo "  HF_TOKEN set — authenticated download (higher rate limits)"
else
    echo "  WARNING: no HF_TOKEN. Anonymous downloads are rate-limited per IP" >&2
    echo "           and RunPod IPs are shared. If this 429s, run on the pod:" >&2
    echo "             huggingface-cli login" >&2
fi

python - <<'PY'
import os
import time

from huggingface_hub import hf_hub_download, snapshot_download

from wegofwd_video.providers.local_diffusion import (
    DEFAULT_MODEL,
    DEFAULT_TRANSFORMER_FILE,
    DEFAULT_TRANSFORMER_REPO,
)

# Retry with backoff: a 429 is often transient, but a shared-IP throttle can
# persist. Fail loudly rather than leaving a half-populated cache that only
# explodes an hour later inside the first render.
for attempt in range(1, 6):
    try:
        print(f"  pipeline repo:   {DEFAULT_MODEL}")
        snapshot_download(DEFAULT_MODEL)
        print(f"  distilled 2B:    {DEFAULT_TRANSFORMER_REPO}/{DEFAULT_TRANSFORMER_FILE}")
        hf_hub_download(DEFAULT_TRANSFORMER_REPO, DEFAULT_TRANSFORMER_FILE)
        print(f"  cache: {os.environ.get('HF_HOME')}")
        break
    except Exception as exc:
        detail = str(exc)[:160].replace("\n", " ")
        print(f"  attempt {attempt}/5 failed: {type(exc).__name__}: {detail}")
        if attempt == 5:
            raise SystemExit(
                "FATAL: could not fetch weights after 5 attempts.\n"
                "If these are 429s, the pod's IP is rate-limited by HuggingFace.\n"
                "Either set HF_TOKEN and re-run, or terminate and redeploy to\n"
                "land on a different host."
            )
        time.sleep(30 * attempt)
PY

du -sh "$HF_HOME"

# ---------------------------------------------------------------------------
# 7. Prove the plan composes before anything expensive runs.
# ---------------------------------------------------------------------------
say smoke

cd "$PRAMANA_DIR"
PYTHONPATH="$PRAMANA_DIR" python scripts/render_variants.py --dry-run

cat <<EOF

$(say ready)

  source $VENV/bin/activate
  export HF_HOME=$HF_HOME PYTHONPATH=$PRAMANA_DIR
  cd $PRAMANA_DIR
  python scripts/render_variants.py --out-dir $WORKSPACE/variants

Pull the results down with runpodctl / scp, then TERMINATE the pod — a stopped
pod still bills for the volume, and an idle running pod bills for the GPU.

DETERMINISM, which is the thing this trades away:
  The SOX pilot spec argues for local rendering on compliance grounds — the
  provider is deterministic=True, so an approved version can be regenerated
  byte-for-byte from its seed. That guarantee is per (seed, torch build, device
  architecture). Rendering here does NOT reproduce the CPU renders, and a
  different GPU model will not reproduce these. Rented still beats the Veo
  Developer API, which rejects `seed` outright — but "regenerate the approved
  version" now means "on this instance type", which is weaker.
  render_variants.py records torch/CUDA/GPU into its results JSON for exactly
  this reason. If any of this footage is ever attested, that block is the
  provenance.
EOF
