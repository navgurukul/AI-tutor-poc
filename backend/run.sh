#!/usr/bin/env bash
# Start the AI Tutor backend. Creates the venv and installs deps on first run.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "==> Creating virtualenv"
  python3 -m venv .venv
  ./.venv/bin/python -m pip install --quiet --upgrade pip
  ./.venv/bin/python -m pip install --quiet -r requirements.txt
fi

if ! curl -sf --max-time 3 "${OLLAMA_HOST:-http://localhost:11434}/api/version" >/dev/null; then
  echo "!! Ollama is not responding. Start it in another terminal: ollama serve" >&2
fi

echo "==> http://localhost:${PORT:-8000}/docs"
exec ./.venv/bin/uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --reload
