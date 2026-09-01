# AI Tutor POC

Proof of concept for an AI tutor that runs **entirely offline**. Speak or type a question
and get an answer back: inference happens locally through [Ollama](https://ollama.com) with
`gemma2:2b` for every language on the backend, with on-device speech-to-text and the
browser's speech synthesizer for the spoken answer on the frontend.
No cloud API, no internet needed once the model and voice assets are downloaded.

```
apps/backend/     FastAPI service wrapping the local Ollama model    (ready)
apps/frontend/    React/Vite web client (STT/TTS tutor flow)         (ready)
apps/desktop/     Borderless desktop launcher for the frontend       (ready)
```

## Quickstart (Windows)

**Prerequisites** — install these first, then the commands below set up and run everything
else:
- [Ollama](https://ollama.com) (the local LLM runtime)
- Python 3.9+ on PATH (the Microsoft Store's `python`/`python3` shims look present but fail
  on first run — install a real one, e.g. `winget install Python.Python.3.12`)
- Node.js 18+ and npm
- Google Chrome or Microsoft Edge

```powershell
ollama pull gemma2:2b        # ~1.6 GB, one-time, needs internet ONCE
ollama serve                 # skip if it already runs as a service

powershell -File scripts\setup.ps1   # install: backend + frontend + desktop deps
powershell -File scripts\start.ps1   # run: starts the backend, then opens the borderless window

powershell -File scripts\create-shortcut.ps1   # optional: "AI Tutor" icon on the desktop
```

`setup.ps1` installs everything (backend Python venv, frontend/desktop npm packages, the
offline Indic speech-to-text model) and creates each app's `.env` from its template. Safe
to re-run — every step is skipped if already done. The spoken answer uses the browser's
built-in speech synthesizer, so there are no voice model files to install; for offline
Hindi/Marathi audio, add that language's speech pack in Windows Settings.

`start.ps1` starts the backend, waits for `/health`, then launches the desktop app in dev
mode (Vite + HMR) and opens the borderless window. Closing the window, or Ctrl+C in the
terminal, stops both. Re-run `start.ps1` any time you restart your machine or the backend/
frontend aren't already running — frontend **code** changes apply live without it, since dev
mode has hot-reload.

`apps/frontend/.env` controls `VITE_USE_MOCK_API` — `setup.ps1` defaults it to `true` (a
self-contained UI with no backend needed, handy for a first look); set it to `false` to talk
to the real backend that `start.ps1` brings up.

## Desktop shortcut

For the target device, where nobody should have to open a terminal: this puts an **AI Tutor**
icon on the desktop that starts the backend, the frontend and the tutor window with one
double-click.

```powershell
powershell -File scripts\create-shortcut.ps1              # Windows: %USERPROFILE%\Desktop\AI Tutor.lnk
powershell -File scripts\create-shortcut.ps1 -StartMenu   # ...and a searchable Start Menu entry
```

```bash
./scripts/create-shortcut.sh          # macOS: ~/Desktop/AI Tutor.app
./scripts/create-shortcut.sh ~/Applications
```

Run `setup.ps1` (or the macOS steps below) first — the shortcut only launches the stack, it
doesn't install it. Both scripts write an **absolute** path to this repo into the shortcut,
so re-run the script after moving or renaming the project folder. Re-running replaces the
shortcut it made previously, and refuses to touch a same-named shortcut it didn't create.

Closing the tutor window leaves the backend and dev server running, which is what makes the
next double-click open instantly. To shut them down: close the minimised PowerShell window
in the taskbar (Windows), or run `./scripts/stop.sh` (macOS/Linux).

If a launch fails there's no console to read on macOS, so the shortcut reports the error in a
dialog and writes the full output to `desktop-launcher.log` in the repo root.

The icon is generated from `apps/desktop/assets/app-icon.svg` — the app's own accent gradient
and favicon bolt, so the desktop icon matches the tutor window. `AI-Tutor.ico` and
`AI-Tutor.icns` are committed, so creating a shortcut needs no image tooling; after editing
the SVGs, regenerate them on macOS with `node scripts/generate-icons.mjs`.

## Backend

Runs on `http://localhost:8000`. Interactive API docs at `/docs`, OpenAPI schema at
`/openapi.json` (usable for generating client types).

See [apps/backend/README.md](apps/backend/README.md) for the full API contract — endpoints,
the SSE streaming format, error codes, configuration, and the known limits of a 1.5B model.

On macOS/Linux, run it directly instead of through the PowerShell scripts above:

```bash
cd apps/backend && ./run.sh
```

`scripts/start.sh` is the macOS/Linux equivalent of `start.ps1` — the backend plus the tutor
window in one command, with `scripts/stop.sh` to shut both down again.

Verify the whole stack end to end:

```bash
cd apps/backend && ./.venv/bin/python smoke_test.py
```

## Frontend

See [apps/frontend/README.md](apps/frontend/README.md) for the full frontend overview and
architecture.

`apps/desktop`'s `npm start` (no `--dev`) serves a production build (`apps/frontend/dist`)
instead of the dev server — rebuild it first with `scripts\build.ps1` (or delete `dist/`)
after any code change, since it's only rebuilt automatically when `dist/` is missing, not
when it's outdated.
