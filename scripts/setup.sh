#!/usr/bin/env bash
# One-shot setup for the AI Tutor POC on macOS/Linux. The counterpart to
# scripts/setup.ps1 on Windows: installs frontend, desktop, and backend
# dependencies, creates local .env files, and downloads the speech model files
# (English + Hindi TTS voices, and the IndicConformer speech-to-text model).
#
# USAGE
#   From anywhere:  ./scripts/setup.sh
#   Safe to re-run - every step is skipped if already done, and a download that
#   was interrupted partway is retried rather than treated as complete.
#
# PREREQUISITES
#   - python3 on PATH (for the backend virtualenv).
#   - Ollama installed and running for the tutor's answers:
#       brew install ollama            # macOS  (or from https://ollama.com)
#       ollama pull <model>            # the model set in apps/backend/.env
#                                      # (OLLAMA_MODEL, default gemma2:2b ~1.6 GB)
#     The exact 'ollama pull ...' line is printed at the end of this script.
#   - ~700 MB of one-time model downloads happen below (IndicConformer ~470 MB,
#     Whisper EN ~145 MB, voices ~130 MB). Resumable - just re-run if the connection drops.
#
#   After this finishes, start everything with:  ./scripts/start.sh
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_dir="$repo_root/apps/frontend"
desktop_dir="$repo_root/apps/desktop"
backend_dir="$repo_root/apps/backend"
models_dir="$frontend_dir/public/models"

c_cyan=$'\033[36m'; c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_gray=$'\033[90m'; c_reset=$'\033[0m'

step()      { printf '\n%s==> %s%s\n' "$c_cyan" "$1" "$c_reset"; }

# exists AND at least $2 bytes - catches partial/corrupt downloads a plain
# `test -f` would wrongly treat as "already done".
valid_file() { [ -f "$1" ] && [ "$(wc -c < "$1" 2>/dev/null || echo 0)" -ge "$2" ]; }

# Download to a temp file first, then move into place, so an interrupted
# download never leaves a corrupt file for a later check to be fooled by.
# Resumes a partial temp file with `-C -`.
download_safely() {
  local url="$1" out="$2" tmp="$2.download"
  if ! curl -fL --retry 3 -C - -o "$tmp" "$url"; then
    rm -f "$tmp"
    echo "Download failed: $url" >&2
    exit 1
  fi
  mv -f "$tmp" "$out"
}

# The LLM is chosen by OLLAMA_MODEL in apps/backend/.env (falls back to the
# template, then gemma2:2b). The "pull the model" hint derives from this.
get_ollama_model() {
  local f
  for f in "$backend_dir/.env" "$backend_dir/.env.example"; do
    if [ -f "$f" ]; then
      local m
      m="$(sed -n 's/^[[:space:]]*OLLAMA_MODEL[[:space:]]*=[[:space:]]*\([^[:space:]]*\).*/\1/p' "$f" | head -n1)"
      if [ -n "$m" ]; then echo "$m"; return; fi
    fi
  done
  echo "gemma2:2b"
}

command -v python3 >/dev/null || { echo "python3 not found on PATH. Install it and re-run." >&2; exit 1; }

# 1. Frontend dependencies.
step "Installing frontend dependencies..."
( cd "$frontend_dir" && npm install )

# 1b. Piper WASM assets (worker script + phonemizer wasm/data). Gate on the
#     ~18 MB data file, not the small worker script that always copies fast.
piper_data="$frontend_dir/public/piper-wasm/piper_phonemize.data"
if ! valid_file "$piper_data" 10000000; then
  step "Fetching Piper WASM assets (react-sts-hooks postinstall didn't run, or was incomplete)..."
  ( cd "$frontend_dir" && npx react-sts-setup )
  valid_file "$piper_data" 10000000 || { echo "Piper WASM assets still missing after react-sts-setup." >&2; exit 1; }
else
  step "Piper WASM assets already present - skipping."
fi

# 2. Desktop launcher.
step "Installing desktop launcher dependencies..."
( cd "$desktop_dir" && npm install )

# 3. Backend virtualenv + Python packages.
backend_python="$backend_dir/.venv/bin/python"
if [ ! -x "$backend_python" ]; then
  step "Creating backend virtualenv..."
  python3 -m venv "$backend_dir/.venv"
else
  step "Backend virtualenv already exists - skipping creation."
fi
step "Installing backend Python packages..."
"$backend_python" -m pip install --quiet --upgrade pip
"$backend_python" -m pip install --quiet -r "$backend_dir/requirements.txt"

# 4. .env files - not committed to git. Copied verbatim: the templates already
#    point the frontend at the local backend (VITE_USE_MOCK_API=false) and set
#    OLLAMA_MODEL for the backend.
if [ ! -f "$backend_dir/.env" ]; then
  step "Creating apps/backend/.env from template..."
  cp "$backend_dir/.env.example" "$backend_dir/.env"
else
  step "apps/backend/.env already exists - leaving it as-is."
fi
if [ ! -f "$frontend_dir/.env" ]; then
  step "Creating apps/frontend/.env from template (points at the local backend)..."
  cp "$frontend_dir/.env.example" "$frontend_dir/.env"
else
  step "apps/frontend/.env already exists - leaving it as-is."
fi

# 5. Piper English voice model (used by the browser's Piper worker).
mkdir -p "$models_dir"
en_base="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium"
if ! valid_file "$models_dir/en_US-amy-medium.onnx" 10000000; then
  step "Downloading Piper voice model (~60MB, one-time)..."
  download_safely "$en_base/en_US-amy-medium.onnx" "$models_dir/en_US-amy-medium.onnx"
else
  step "Voice model (.onnx) already present - skipping download."
fi
if ! valid_file "$models_dir/en_US-amy-medium.json" 100; then
  step "Downloading Piper voice config..."
  download_safely "$en_base/en_US-amy-medium.onnx.json" "$models_dir/en_US-amy-medium.json"
else
  step "Voice model config already present - skipping download."
fi

# 6. Offline speech-to-text: AI4Bharat IndicConformer-600M (CTC), run by the
#    backend via sherpa-onnx (installed with the other Python packages above).
#    fp32 export ~470 MB, covers Hindi/Marathi.
indic_dir="$backend_dir/models/indicconformer"
indic_base="https://huggingface.co/meetsync/indic-conformer-onnx-sherpa/resolve/main"
mkdir -p "$indic_dir"
if ! valid_file "$indic_dir/model.onnx" 314572800; then
  step "Downloading IndicConformer-600M STT model (~470MB, one-time)..."
  download_safely "$indic_base/model.onnx?download=true" "$indic_dir/model.onnx"
else
  step "IndicConformer STT model already present - skipping download."
fi
if ! valid_file "$indic_dir/tokens.txt" 10000; then
  step "Downloading IndicConformer STT tokens..."
  download_safely "$indic_base/tokens.txt?download=true" "$indic_dir/tokens.txt"
else
  step "IndicConformer STT tokens already present - skipping."
fi

# 6b. Offline English speech-to-text: Whisper base.en (int8) - handles
#     Indian-accented English well. Same sherpa-onnx wheel.
en_stt_name="sherpa-onnx-whisper-base.en"
en_stt_dir="$backend_dir/models/stt/$en_stt_name"
en_stt_archive="$backend_dir/models/stt/$en_stt_name.tar.bz2"
en_stt_url="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$en_stt_name.tar.bz2"
if ! ls "$en_stt_dir"/*tokens.txt >/dev/null 2>&1; then
  mkdir -p "$backend_dir/models/stt"
  step "Downloading English STT model ($en_stt_name, ~145MB, one-time)..."
  download_safely "$en_stt_url" "$en_stt_archive"
  step "Extracting English STT model..."
  tar -xf "$en_stt_archive" -C "$backend_dir/models/stt"
  rm -f "$en_stt_archive"
  # The tarball ships both fp32 and int8; we only load int8 - drop the ~290MB
  # of fp32 encoder/decoder.
  rm -f "$en_stt_dir"/*-encoder.onnx "$en_stt_dir"/*-decoder.onnx
else
  step "English STT model already present - skipping download."
fi

# 7. Offline text-to-speech for non-English answers: a Piper VITS voice
#    (hi_IN-priyamvada, female), run by the backend through the same sherpa-onnx.
tts_name="vits-piper-hi_IN-priyamvada-medium"
tts_dir="$backend_dir/models/tts/$tts_name"
tts_archive="$backend_dir/models/tts/$tts_name.tar.bz2"
tts_url="https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/$tts_name.tar.bz2"
if [ ! -f "$tts_dir/tokens.txt" ]; then
  mkdir -p "$backend_dir/models/tts"
  step "Downloading Piper TTS voice ($tts_name, ~60MB, one-time)..."
  download_safely "$tts_url" "$tts_archive"
  step "Extracting Piper TTS voice..."
  tar -xf "$tts_archive" -C "$backend_dir/models/tts"
  rm -f "$tts_archive"
else
  step "Piper TTS voice already present - skipping download."
fi

ollama_model="$(get_ollama_model)"

printf '\n%sSetup complete.%s\n\n' "$c_green" "$c_reset"
printf '%sOne prerequisite start.sh does NOT install for you:%s\n' "$c_yellow" "$c_reset"
printf '%s  Ollama must be installed and running, with the model pulled:%s\n' "$c_yellow" "$c_reset"
printf '%s    brew install ollama          # or https://ollama.com%s\n' "$c_yellow" "$c_reset"
printf '%s    ollama pull %s   # OLLAMA_MODEL in apps/backend/.env%s\n' "$c_yellow" "$ollama_model" "$c_reset"
printf '%s  Without it the app still opens but replies show "model unavailable".%s\n\n' "$c_gray" "$c_reset"
printf '%sThen: ./scripts/start.sh%s\n' "$c_green" "$c_reset"
