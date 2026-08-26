# AI Tutor POC

Proof of concept for an AI tutor that runs **entirely offline**. Speak or type a question
and get an answer back: inference happens locally through [Ollama](https://ollama.com) with
`qwen2.5:1.5b` on the backend, with on-device speech-to-text and Piper TTS on the frontend.
No cloud API, no internet needed once the model and voice assets are downloaded.

```
apps/backend/     FastAPI service wrapping the local Ollama model    (ready)
apps/frontend/    React/Vite web client (STT/TTS tutor flow)         (ready)
apps/desktop/     Borderless desktop launcher for the frontend       (ready)
```

## Backend

```bash
ollama pull qwen2.5:1.5b     # one-time, ~1 GB, needs internet ONCE
ollama serve                 # skip if it already runs as a service
cd apps/backend && ./run.sh
```

Runs on `http://localhost:8000`. Interactive API docs at `/docs`, OpenAPI schema at
`/openapi.json` (usable for generating client types).

Verify the whole stack end to end:

```bash
cd apps/backend && ./.venv/bin/python smoke_test.py
```

See [apps/backend/README.md](apps/backend/README.md) for the full API contract — endpoints,
the SSE streaming format, error codes, configuration, and the known limits of a 1.5B model.

## Frontend

**Prerequisites:** Node.js 18+, npm, and Google Chrome or Microsoft Edge installed.

From the repo root, on Windows:

```powershell
powershell -File scripts\setup.ps1
```

This installs dependencies for `apps/frontend` and `apps/desktop`, creates
`apps/frontend/.env` (mock API mode on, so no backend is needed to try it), and downloads
the Piper voice model files. Safe to re-run — each step is skipped if already done.

Run it:

```bash
cd apps/desktop
npm start
```

Opens the AI Tutor in a borderless window. Rebuild after code changes with:

```powershell
powershell -File scripts\build.ps1
```

See [apps/frontend/README.md](apps/frontend/README.md) for the full frontend overview and
architecture. To talk to a real backend instead of the mock data, set
`VITE_USE_MOCK_API=false` in `apps/frontend/.env` (see `apps/frontend/.env.example`) — CORS
is open by default (`CORS_ORIGINS=*`) so the dev server works out of the box.
