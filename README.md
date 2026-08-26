# AI Tutor POC

Proof of concept for an AI tutor that runs **entirely offline**. All inference happens
locally through [Ollama](https://ollama.com) with `qwen2.5:1.5b` — no cloud API, no internet
needed once the model is pulled.

```
backend/      FastAPI service wrapping the local Ollama model  (ready)
frontend/     Web client                                       (in progress)
```

## Backend

```bash
ollama pull qwen2.5:1.5b     # one-time, ~1 GB, needs internet ONCE
ollama serve                 # skip if it already runs as a service
cd backend && ./run.sh
```

Runs on `http://localhost:8000`. Interactive API docs at `/docs`, OpenAPI schema at
`/openapi.json` (usable for generating client types).

Verify the whole stack end to end:

```bash
cd backend && ./.venv/bin/python smoke_test.py
```

See [backend/README.md](backend/README.md) for the full API contract — endpoints, the SSE
streaming format, error codes, configuration, and the known limits of a 1.5B model.

## Frontend

Not started yet. It should talk to the backend over HTTP on port 8000; CORS is open by
default (`CORS_ORIGINS=*`) so any dev server origin works out of the box.

The two endpoints to build against first:

- `POST /api/chat/stream` — the chat UI, token-by-token over Server-Sent Events.
- `GET /health` — returns 200 even when Ollama is down, reporting `status: "degraded"` plus
  a fix hint, so the app can show an "offline model ready" indicator on boot.
