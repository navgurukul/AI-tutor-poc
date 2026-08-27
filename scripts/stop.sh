#!/usr/bin/env bash
# Stops the AI Tutor stack on macOS/Linux.
#
# Closing the tutor window doesn't stop anything behind it - the Chrome window
# is launched detached, so the backend and the Vite dev server keep running
# (which is what makes the next double-click of the desktop shortcut instant).
# This is how you shut those down.
#
#   ./scripts/stop.sh
set -uo pipefail

stopped=false

for entry in "8000:backend" "5180:frontend (dev)" "4173:frontend (preview)"; do
  port="${entry%%:*}"
  label="${entry#*:}"
  pids="$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    # SIGTERM first so uvicorn and Vite can close their sockets; only escalate
    # to SIGKILL for anything still holding the port a moment later.
    kill $pids 2>/dev/null || true
    sleep 1
    still="$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)"
    [ -n "$still" ] && kill -9 $still 2>/dev/null || true
    echo "Stopped $label (port $port)"
    stopped=true
  fi
done

if [ "$stopped" != true ]; then
  echo "Nothing to stop - no AI Tutor services are listening."
fi

echo "Ollama is left running; stop it yourself if you want it down too."
