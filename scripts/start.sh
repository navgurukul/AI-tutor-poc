#!/usr/bin/env bash
# Starts the full AI Tutor stack on macOS/Linux: the backend (FastAPI/uvicorn)
# in the background, then the desktop app, which starts the frontend and opens
# it in a borderless window. The counterpart to scripts/start.ps1 on Windows.
#
# USAGE
#   From anywhere:  ./scripts/start.sh
#
#   Requires Ollama running locally (`ollama serve`) with the configured model
#   pulled. The model is OLLAMA_MODEL in apps/backend/.env (default gemma2:2b);
#   this script prints the exact `ollama pull ...` line for whatever you've set.
#   The backend starts without it, but /health reports degraded and chat
#   requests fail until it's reachable.
#
#   Closing the borderless window, or Ctrl+C here, stops the frontend; the
#   backend is stopped too, but only if this script was the one that started
#   it (see below).
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_dir="$repo_root/apps/backend"
desktop_dir="$repo_root/apps/desktop"
backend_python="$backend_dir/.venv/bin/python"
backend_out_log="$repo_root/backend.out.log"
backend_err_log="$repo_root/backend.err.log"

# Set when we start the backend ourselves. If a backend was already listening
# on :8000 when we arrived - someone's `run.sh` in another terminal, or an
# earlier launch that outlived its window - it isn't ours to shut down, and
# killing it on exit would yank the server out from under that other session.
backend_is_ours=false

c_cyan=$'\033[36m'; c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_reset=$'\033[0m'

url_ok() { curl -sf --max-time 2 "$1" >/dev/null 2>&1; }

# Which LLM the backend expects - OLLAMA_MODEL in apps/backend/.env, falling
# back to the template, then gemma2:2b. The checks below follow it.
get_ollama_model() {
  local f m
  for f in "$backend_dir/.env" "$backend_dir/.env.example"; do
    if [ -f "$f" ]; then
      m="$(sed -n 's/^[[:space:]]*OLLAMA_MODEL[[:space:]]*=[[:space:]]*\([^[:space:]]*\).*/\1/p' "$f" | head -n1)"
      if [ -n "$m" ]; then echo "$m"; return; fi
    fi
  done
  echo "gemma2:2b"
}
ollama_model="$(get_ollama_model)"

stop_port() {
  # Kill by the port's listener rather than a remembered PID: uvicorn reloads
  # and shell wrappers mean the PID we spawned isn't reliably the one holding
  # the port, and freeing the port is what actually matters for the next run.
  local pids
  pids="$(lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null || true)"
  [ -n "$pids" ] && kill $pids 2>/dev/null || true
}

cleanup() {
  if [ "$backend_is_ours" = true ]; then
    printf '\n%s==> Stopping backend...%s\n' "$c_cyan" "$c_reset"
    stop_port 8000
  fi
}
trap cleanup EXIT INT TERM

ollama_host="${OLLAMA_HOST:-http://localhost:11434}"
printf '\n%s==> Checking Ollama (%s)...%s\n' "$c_cyan" "$ollama_model" "$c_reset"
if url_ok "$ollama_host/api/version"; then
  if curl -sf --max-time 3 "$ollama_host/api/tags" 2>/dev/null | grep -q -- "$ollama_model"; then
    printf "%sOllama is up, '%s' is pulled.%s\n" "$c_green" "$ollama_model" "$c_reset"
  else
    printf "%sOllama is up, but '%s' isn't pulled yet.  Run:  ollama pull %s%s\n" \
      "$c_yellow" "$ollama_model" "$ollama_model" "$c_reset"
    printf '%s  (or set OLLAMA_MODEL in apps/backend/.env to one you have). Continuing.%s\n' "$c_yellow" "$c_reset"
  fi
else
  printf "%sOllama isn't responding on %s - start it ('ollama serve'), then:  ollama pull %s%s\n" \
    "$c_yellow" "$ollama_host" "$ollama_model" "$c_reset"
  printf '%s  Continuing anyway; /health reports degraded until it is reachable.%s\n' "$c_yellow" "$c_reset"
fi

printf '\n%s==> Starting backend on http://localhost:8000 ...%s\n' "$c_cyan" "$c_reset"
if url_ok "http://localhost:8000/health"; then
  printf '%sBackend is already running - reusing it.%s\n' "$c_green" "$c_reset"
else
  if [ ! -x "$backend_python" ]; then
    echo "Backend virtualenv not found at $backend_python." >&2
    echo "Create it first:  cd apps/backend && ./run.sh   (Ctrl+C once it's up)" >&2
    exit 1
  fi

  # No --reload here, unlike run.sh: the reloader spawns a second process that
  # survives naive PID kills, and a launcher window doesn't want the backend
  # restarting under it mid-answer. Frontend code still hot-reloads.
  (cd "$backend_dir" && exec "$backend_python" -m uvicorn app.main:app \
      --host 0.0.0.0 --port 8000 >"$backend_out_log" 2>"$backend_err_log") &
  backend_is_ours=true

  ready=false
  for _ in $(seq 1 30); do
    if url_ok "http://localhost:8000/health"; then ready=true; break; fi
    sleep 1
  done
  if [ "$ready" != true ]; then
    echo "Backend did not become healthy within 30s. Check $backend_err_log" >&2
    exit 1
  fi
  printf '%sBackend ready. Logs: %s / %s%s\n' "$c_green" "$backend_out_log" "$backend_err_log" "$c_reset"
fi

printf '\n%s==> Starting desktop app (frontend + borderless window)...%s\n' "$c_cyan" "$c_reset"
# Dev mode (Vite dev server, always fresh) rather than `npm start`'s production
# build+preview - launch.mjs only rebuilds dist/ when it's missing, not when
# it's stale, so production mode can silently serve old code.
cd "$desktop_dir" && npm run dev
