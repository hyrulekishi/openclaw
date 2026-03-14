#!/usr/bin/env bash
set -euo pipefail

ROOT="${MEDIA_PIPELINE_ROOT:-$HOME/.openclaw/workspace/tools/media-pipeline}"
VENV="$ROOT/.venv"
REQ="$ROOT/requirements.txt"
DEFAULT_CFG="$ROOT/config/default.yaml"

ok() { echo "✅ $1"; }
warn() { echo "⚠️  $1"; }
err() { echo "❌ $1"; }
info() { echo "• $1"; }

section() {
  echo
  echo "== $1 =="
}

has_cmd() { command -v "$1" >/dev/null 2>&1; }

section "Media Pipeline Doctor"
info "root: $ROOT"

section "Base files"
[ -f "$DEFAULT_CFG" ] && ok "config/default.yaml found" || err "config/default.yaml missing"
[ -f "$REQ" ] && ok "requirements.txt found" || err "requirements.txt missing"

section "System commands"
if has_cmd python3; then
  ok "python3: $(python3 --version 2>/dev/null)"
else
  err "python3 not found"
fi

if has_cmd ffmpeg; then
  ok "ffmpeg: $(ffmpeg -version 2>/dev/null | head -n 1)"
else
  warn "ffmpeg not found (required for audio extraction/normalization)"
fi

if has_cmd yt-dlp; then
  ok "yt-dlp: $(yt-dlp --version 2>/dev/null | head -n 1)"
else
  warn "yt-dlp not found (needed for URL/media fetching)"
fi

if has_cmd nvidia-smi; then
  ok "nvidia-smi available"
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/  • /'
else
  if [ -f /usr/lib/wsl/lib/nvidia-smi ]; then
    ok "WSL nvidia-smi available at /usr/lib/wsl/lib/nvidia-smi"
    /usr/lib/wsl/lib/nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/  • /'
  else
    warn "nvidia-smi not visible in current shell"
  fi
fi

section "Python virtual environment"
if [ -d "$VENV" ]; then
  ok "venv exists: $VENV"
  if [ -x "$VENV/bin/python" ]; then
    ok "venv python: $($VENV/bin/python --version 2>/dev/null)"
  else
    warn "venv exists but python executable missing"
  fi
else
  warn "venv not created yet: $VENV"
fi

section "Python packages"
if [ -x "$VENV/bin/python" ]; then
  "$VENV/bin/python" - <<'PY'
mods = ["faster_whisper", "ctranslate2", "huggingface_hub", "torch"]
for m in mods:
    try:
        __import__(m)
        print(f"✅ python package: {m}")
    except Exception as e:
        print(f"⚠️  python package missing/unavailable: {m}")

try:
    import torch
    if torch.cuda.is_available():
        print(f"✅ torch cuda available: {torch.cuda.get_device_name(0)}")
    else:
        print("⚠️  torch installed but CUDA not available")
except Exception:
    pass
PY
else
  warn "skip package import checks (venv missing)"
fi

section "Recommended next step"
if [ ! -d "$VENV" ]; then
  info "Create venv and install requirements first"
  echo "  python3 -m venv $VENV"
  echo "  $VENV/bin/pip install -r $REQ"
elif ! [ -x "$VENV/bin/python" ]; then
  info "Repair venv python executable"
else
  info "If ffmpeg and packages are ready, next implement/exercise transcribe.py"
fi
