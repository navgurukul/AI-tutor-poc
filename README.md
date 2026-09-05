# AI Tutor POC

Proof of concept for an AI tutor that runs **entirely offline**. Speak or type a question
and get an answer back: inference happens locally through [Ollama](https://ollama.com) with
`gemma2:2b` for every language on the backend; speech-to-text is on the backend
(sherpa-onnx), and the spoken answer is synthesized in the browser (Piper WASM for
English/Hindi, the OS voice for Marathi). No cloud API, no internet needed once the model
and voice assets are downloaded.

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

**macOS/Linux** — same flow with the shell scripts:

```bash
brew install ollama && ollama serve &   # or from https://ollama.com
ollama pull gemma2:2b

./scripts/setup.sh     # install deps for all 3 apps + model downloads + .env files
./scripts/start.sh     # backend + borderless tutor window  (./scripts/stop.sh to shut down)
./scripts/create-shortcut.sh            # optional: ~/Desktop/AI Tutor.app
```

`setup.ps1` installs everything (backend Python venv, frontend/desktop npm packages) and
downloads the model files — backend speech-to-text (IndicConformer ~470 MB for Hindi/Marathi,
Whisper base.en ~155 MB for English) and the browser Piper voices for English and Hindi
(`en_US-amy-low`, `hi_IN-priyamvada-medium`). It also creates each app's `.env` from its
template. About 700 MB of one-time, resumable downloads; safe to re-run — every step is
skipped if already done. Marathi has no Piper voice, so its spoken answer falls back to the
OS speechSynthesis voice (add the Windows Marathi speech pack, or it stays silent).

`start.ps1` starts the backend, waits for `/health`, then launches the desktop app in dev
mode (Vite + HMR) and opens the borderless window. Closing the window, or Ctrl+C in the
terminal, stops both. Re-run `start.ps1` any time you restart your machine or the backend/
frontend aren't already running — frontend **code** changes apply live without it, since dev
mode has hot-reload.

`apps/frontend/.env` controls `VITE_USE_MOCK_API` — `setup.ps1` copies the template as-is,
so it defaults to `false` (talks to the real backend that `start.ps1` brings up). Set it to
`true` for a self-contained UI with canned replies and no backend.

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

Run `setup.ps1` (Windows) or `setup.sh` (macOS/Linux) first — the shortcut only launches the
stack, it doesn't install it. Both scripts write an **absolute** path to this repo into the shortcut,
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

## Textbook library (RAG)

The tutor can answer from the school's own textbooks instead of the model's
general knowledge. Open **Library** in the app bar (or `#setup` in the URL),
upload a PDF, tag it with a class and subject, and it is cleaned, split and
indexed on the device. Ask a question afterwards and the reply is grounded in
those pages, with the chapter and page number cited back.

```
ollama pull nomic-embed-text     # one-time, ~274 MB, the retrieval model
```

Retrieval is **additive**: with no library, or with the store unavailable, the
tutor answers exactly as it did before and `/health` explains why. Nothing here
reaches the internet.

**Python 3.11+ is now required.** Vector search runs on `sqlite-vec`, a SQLite
extension, and macOS's system Python 3.9 is built without extension loading, so
it cannot load it at all. On Windows `winget install Python.Python.3.12` (which
`setup.ps1` already suggests) is fine; on macOS, recreate the venv with a
Python from python.org or Homebrew. The backend still *starts* on 3.9 -- it
just reports the library as unavailable and skips retrieval.

Everything lives in one file, `apps/backend/data/library.db`. That is
deliberate: embedding a full textbook takes minutes on the target laptops and
the better part of a day on the oldest of them, so build the index once on a
fast machine and **copy the .db onto each device** rather than ingesting per
device. The file carries the text, the metadata and the vectors together.

Tuning lives in `apps/backend/.env` (see `.env.example`): `RAG_TOP_K` trades
answer grounding against prefill time, and `RAG_MAX_DISTANCE` is the relevance
cut-off. The default of 0.42 was measured, not guessed -- on a Class 9 Science
chapter, questions the text answers scored 0.12-0.34 and off-topic ones scored
0.50-0.58. Re-measure with `POST /api/library/search` if you change
`RAG_EMBEDDING_MODEL`, and note that changing it means re-ingesting: vectors
from two models cannot be compared, and the store refuses to mix them.

## Backend

Runs on `http://localhost:8000`. Interactive API docs at `/docs`, OpenAPI schema at
`/openapi.json` (usable for generating client types).

See [apps/backend/README.md](apps/backend/README.md) for the full API contract — endpoints,
the SSE streaming format, error codes, configuration, and the known limits of a 1.5B model.

On macOS/Linux, use the shell equivalents of the PowerShell scripts:

```bash
./scripts/setup.sh   # install deps for all 3 apps + model downloads + .env files
./scripts/start.sh   # backend + tutor window in one command  (./scripts/stop.sh to shut down)
```

`setup.sh` / `start.sh` mirror `setup.ps1` / `start.ps1` step for step (they use the venv's
`bin/` instead of `Scripts/`, `curl` instead of `Invoke-WebRequest`, etc.). To run just the
backend on its own: `cd apps/backend && ./run.sh`.

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
