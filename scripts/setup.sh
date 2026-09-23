#!/usr/bin/env bash
# One-shot setup for the AI Tutor POC on macOS/Linux. The counterpart to
# scripts/setup.ps1 on Windows: installs frontend, desktop, and backend
# dependencies, creates local .env files, downloads the speech model files
# (backend TTS voices, and the speech-to-text models), and installs Ollama with
# the tutor's LLM (sarvam-1-chat) and embedding model (bge-m3).
#
# USAGE
#   From anywhere:  ./scripts/setup.sh
#   Safe to re-run - every step is skipped if already done, and a download that
#   was interrupted partway is retried rather than treated as complete.
#
# PREREQUISITES
#   - python3, node/npm and curl on PATH.
#   - Ollama is installed if missing (Homebrew on macOS, the official install
#     script on Linux, which asks for sudo), started if not running, and given
#     the models in apps/backend/.env: OLLAMA_MODEL (default sarvam-1-chat,
#     built from scripts/sarvam-1-chat.Modelfile, ~1.5 GB) and
#     RAG_EMBEDDING_MODEL (default bge-m3, ~1.2 GB).
#   - ~850 MB of speech model downloads (IndicConformer ~470 MB, Whisper EN
#     ~145 MB, backend TTS voices ~200 MB) plus ~2.7 GB of Ollama models, all
#     one-time. Resumable - just re-run if the connection drops.
#
#   After this finishes, start everything with:  ./scripts/start.sh
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_dir="$repo_root/apps/frontend"
desktop_dir="$repo_root/apps/desktop"
backend_dir="$repo_root/apps/backend"

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

# A setting from apps/backend/.env, falling back to the template, then to $2.
get_env_value() {
  local f v
  for f in "$backend_dir/.env" "$backend_dir/.env.example"; do
    if [ -f "$f" ]; then
      v="$(sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*\([^[:space:]]*\).*/\1/p" "$f" | head -n1)"
      if [ -n "$v" ]; then echo "$v"; return; fi
    fi
  done
  echo "$2"
}

# The LLM is chosen by OLLAMA_MODEL in apps/backend/.env (falls back to the
# template, then sarvam-1-chat). Step 7 installs whatever this says.
get_ollama_model() { get_env_value OLLAMA_MODEL sarvam-1-chat; }

command -v python3 >/dev/null || { echo "python3 not found on PATH. Install it and re-run." >&2; exit 1; }

# 1. Frontend dependencies.
step "Installing frontend dependencies..."
( cd "$frontend_dir" && npm install )


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

# 5. Backend text-to-speech voices: Piper, run by sherpa-onnx on the backend.
#    scripts/package_tts_voices.py downloads English/Hindi/Marathi from the
#    official rhasspy/piper-voices repo into apps/backend/models/tts/. It needs
#    the `onnx` package, which the tutor itself does not, so it is installed
#    here rather than in requirements.txt.
if ! valid_file "$backend_dir/models/tts/hindi/model.onnx" 10000000; then
  step "Packaging the backend TTS voices (English/Hindi/Marathi, ~200MB, one-time)..."
  "$backend_dir/.venv/bin/python" -m pip install --quiet onnx
  "$backend_dir/.venv/bin/python" "$repo_root/scripts/package_tts_voices.py"
else
  step "Backend TTS voices already present - skipping."
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


# 7. Ollama and the models the backend asks for. Every sub-step is skipped when
#    already done, so a re-run costs a few seconds.
ollama_host="$(get_env_value OLLAMA_HOST http://localhost:11434)"
ollama_model="$(get_ollama_model)"
embed_model="$(get_env_value RAG_EMBEDDING_MODEL bge-m3)"

if ! command -v ollama >/dev/null 2>&1; then
  if [ "$(uname)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
    step "Installing Ollama with Homebrew..."
    brew install ollama
  elif [ "$(uname)" = "Linux" ]; then
    step "Installing Ollama with the official install script (asks for sudo)..."
    curl -fsSL https://ollama.com/install.sh | sh
  else
    echo "Ollama is not installed. Install it from https://ollama.com and re-run." >&2
    exit 1
  fi
else
  step "Ollama already installed - skipping."
fi

if ! curl -sf --max-time 2 "$ollama_host/api/version" >/dev/null 2>&1; then
  step "Starting the Ollama server in the background (log: ollama.log)..."
  # nohup so it outlives this script: start.sh expects it running.
  OLLAMA_HOST="${ollama_host#http://}" nohup ollama serve >"$repo_root/ollama.log" 2>&1 &
  for _ in $(seq 1 30); do
    curl -sf --max-time 2 "$ollama_host/api/version" >/dev/null 2>&1 && break
    sleep 1
  done
  curl -sf --max-time 2 "$ollama_host/api/version" >/dev/null 2>&1 || {
    echo "Ollama did not come up on $ollama_host - see ollama.log." >&2
    exit 1
  }
else
  step "Ollama server already running - skipping."
fi

# Whether `ollama list` has a model, with or without its implicit :latest tag.
have_model() {
  local want="$1"
  case "$want" in *:*) ;; *) want="$want:latest" ;; esac
  ollama list | awk 'NR > 1 { print $1 }' | grep -qxF -- "$want"
}

ensure_model() {
  local name="${1%%:*}" mf base
  mf="$repo_root/scripts/$name.Modelfile"
  if [ -f "$mf" ]; then
    # Built locally from its base weights -- `ollama pull` cannot fetch it.
    base="$(sed -n 's/^FROM[[:space:]]*//p' "$mf" | head -n1)"
    if have_model "$base"; then
      step "Base weights $base already pulled - skipping download."
    else
      step "Pulling $base (one-time)..."
      ollama pull "$base"
    fi
    # Always re-created: it reuses the pulled weights (about a second), and
    # keeps the model in step with any edit to its Modelfile.
    step "Building $name from scripts/$name.Modelfile..."
    ollama create "$name" -f "$mf"
  elif have_model "$1"; then
    step "$1 already pulled - skipping."
  else
    step "Pulling $1 (one-time)..."
    ollama pull "$1"
  fi
}

ensure_model "$ollama_model"
ensure_model "$embed_model"

printf '\n%sSetup complete.%s LLM: %s, embeddings: %s\n' "$c_green" "$c_reset" "$ollama_model" "$embed_model"
printf '%sThen: ./scripts/start.sh%s\n' "$c_green" "$c_reset"
