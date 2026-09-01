# AI Tutor POC — Offline LLM Backend

FastAPI backend for an AI tutor that runs **entirely offline**. Every completion is
generated locally by [Ollama](https://ollama.com) using `gemma2:2b` (one model for
every language — see the `OLLAMA_MODEL` note below) — no external API calls, no
internet needed at request time.

Frontend developers: the full interactive API reference is at **http://localhost:8000/docs**
once the server is running, and the OpenAPI schema at `/openapi.json` can generate types.

> Every command and path in this document is relative to this `apps/backend/` directory.
> The frontend lives alongside it in `apps/frontend/`.

---

## Quickstart

```bash
# 1. One-time: install the model (needs internet ONCE, ~1.6 GB)
ollama pull gemma2:2b

# 2. Make sure the Ollama daemon is running
ollama serve          # skip if it already runs as a service

# 3. Start the backend (creates the venv and installs deps on first run)
cd apps/backend && ./run.sh
```

The API is then on `http://localhost:8000`, docs on `/docs`.

Verify the whole stack end to end:

```bash
./.venv/bin/python smoke_test.py
```

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Backend + Ollama + model status. Never 5xx. |
| `GET` | `/api/models` | Locally installed models. |
| `POST` | `/api/chat` | Send a message, get the whole reply. |
| `POST` | `/api/chat/stream` | Same, streamed token by token (SSE). |
| `GET` | `/api/chat/stream` | Stream variant for native `EventSource`. |
| `GET` | `/api/stt` | Is offline speech-to-text ready? Also triggers the lazy model load. |
| `POST` | `/api/stt` | Transcribe a short 16 kHz mono WAV (raw body) → `{ "text": ... }`. Indian languages only. |
| `POST` | `/api/tutor/explain` | Structured explainer card for a topic. |
| `POST` | `/api/tutor/quiz` | Generate multiple-choice questions. |
| `POST` | `/api/tutor/evaluate` | Grade a student's answer. |
| `POST` | `/api/sessions` | Create a session explicitly (optional). |
| `GET` | `/api/sessions` | List active sessions. |
| `GET` | `/api/sessions/{id}` | Full transcript. |
| `DELETE` | `/api/sessions/{id}` | Delete a session. |

### `GET /health`

Call this on app boot to drive an "offline model ready" indicator. It returns **200 even
when Ollama is down**, reporting `status: "degraded"` so you can render a fix hint instead
of handling a network error.

```json
{
  "status": "ok",
  "offline": true,
  "ollama": { "reachable": true, "host": "http://localhost:11434", "version": "0.32.15" },
  "model": { "name": "qwen2.5:1.5b", "available": true, "available_models": ["qwen2.5:1.5b"] },
  "active_sessions": 2
}
```

### `POST /api/chat`

```jsonc
// request
{
  "message": "Why does ice float?",
  "session_id": "optional - omit to start a new conversation",
  "profile": {                    // applied when the session is created
    "subject": "Science",
    "level": "Grade 7",
    "style": "socratic",          // socratic | direct | exam_prep
    "language": "English",
    "student_name": "Aisha"
  },
  "temperature": 0.7,             // optional
  "max_tokens": 800,              // optional
  "model": "qwen2.5:1.5b"         // optional
}
```

```jsonc
// response
{
  "session_id": "52f3b3ffb1cf4df294a9751712d34d96",
  "reply": "Good question! Think about what happens when water freezes...",
  "model": "qwen2.5:1.5b",
  "usage": {
    "prompt_tokens": 136, "completion_tokens": 63,
    "total_duration_ms": 3384, "load_duration_ms": 1,
    "tokens_per_second": 24.59
  },
  "created_at": "2026-08-26T10:50:38.856325Z"
}
```

**Sessions are automatic.** Omit `session_id` on the first message, store the one you get
back, and send it with every subsequent message. Conversation history is replayed to the
model, so follow-ups like "explain that more simply" work. An unknown or expired
`session_id` silently starts a fresh session rather than erroring, so a stale id in
`localStorage` after a server restart won't break the UI.

> **Warm-up:** the frontend fires one throwaway `POST /api/chat` with `max_tokens: 1` and
> the session profile as soon as its page loads, then discards the reply. That loads the
> model (~10 s cold-start) and lets Ollama cache the system-prompt prefix, so the
> student's first real question is fast. It's just a normal chat call — no special
> endpoint — so expect one extra 1-token generation and one throwaway session per page
> load (evicted by TTL/LRU).

### `POST /api/chat/stream` — SSE

Each SSE frame is `data: {json}`, and the stream always ends with `data: [DONE]`.

| `type` | Payload |
|---|---|
| `start` | `session_id`, `model` |
| `token` | `content` — append to the reply as it arrives |
| `done` | `session_id`, `reply` (full text), `usage` |
| `error` | `detail`, `hint` |

```js
const res = await fetch("http://localhost:8000/api/chat/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message, session_id: sessionId }),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  const frames = buffer.split("\n\n");
  buffer = frames.pop();                       // keep the incomplete tail

  for (const frame of frames) {
    if (!frame.startsWith("data: ")) continue;
    const payload = frame.slice(6);
    if (payload === "[DONE]") return;

    const event = JSON.parse(payload);
    if (event.type === "start") setSessionId(event.session_id);
    if (event.type === "token") appendToReply(event.content);
    if (event.type === "done")  setUsage(event.usage);
    if (event.type === "error") showError(event.detail, event.hint);
  }
}
```

Prefer this over `/api/chat` for the chat UI — a 1.5B model streams at ~25 tokens/sec, so
a buffered reply feels slow while a streamed one feels instant.

If you'd rather use the browser's native `EventSource` (GET only):

```js
const es = new EventSource(
  `http://localhost:8000/api/chat/stream?message=${encodeURIComponent(msg)}&session_id=${sid}`
);
```

### `POST /api/tutor/explain`

Request `{ "topic": "Photosynthesis", "level": "Grade 8" }` returns a card you can render
directly — no prose parsing:

```json
{
  "summary": "Photosynthesis is how plants make their food using sunlight.",
  "key_points": ["Plants use sunlight to turn water and carbon dioxide into sugar.", "..."],
  "analogy": "Like a factory where plants make food using sunlight as the power source.",
  "check_question": "Can you explain how plants make food using sunlight?"
}
```

### `POST /api/tutor/quiz`

```jsonc
{ "topic": "The water cycle", "num_questions": 3, "num_options": 4,
  "difficulty": "medium", "level": "Grade 6" }   // difficulty: easy | medium | hard
```

Returns `questions[]`, each with `question`, `options[]`, a **0-based** `answer_index`, and
an `explanation`. `num_questions` and `num_options` are honoured exactly.

> Generation takes ~10-15s for 3 questions on CPU. Show a loading state.

### `POST /api/tutor/evaluate`

```jsonc
{ "question": "Why do we have seasons?",
  "student_answer": "Because Earth gets closer to the sun in summer.",
  "expected_answer": "Because Earth's axis is tilted.",   // optional
  "level": "Grade 7" }
```

Returns `verdict` (`correct` | `partially_correct` | `incorrect`), `score` (0-100),
`feedback` (addressed to the student) and `hint`.

### `POST /api/stt` — offline speech-to-text (Indian languages)

Send a short **16 kHz mono 16-bit WAV** as the raw request body
(`Content-Type: audio/wav`); get `{ "text": "..." }` back. Used by the frontend
for **Hindi / Marathi** — English speech input is recognised on-device by the
browser and never reaches the backend.

Runs [`sherpa-onnx`](https://pypi.org/project/sherpa-onnx/) (a prebuilt wheel,
installed with the other requirements — no compiler) with AI4Bharat's
**IndicConformer-600M** CTC model. One multilingual model emits the correct
native script — no language auto-detect, so no Hindi/Urdu confusion. A clip
decodes in ~1–3 s on CPU (batch, no live partials).

- Model files: `apps/backend/models/indicconformer/{model.onnx,tokens.txt}`,
  downloaded by `scripts/setup.ps1`. Override the folder with `STT_MODEL_DIR`,
  the ONNX filename with `STT_MODEL_FILE`.
- Default is the **fp32** export (`model.onnx`, ~470 MB). `model.int8.onnx`
  (~188 MB) is available but roughly doubles the word-error rate (Hindi CTC
  ~0.16 → ~0.30), so it's opt-in via `STT_MODEL_FILE`.
- Loaded lazily on the first `/api/stt` call (or `GET /api/stt`), so an
  English-only session pays nothing.
- Missing model / wheel → `503` with a "run setup" hint, not a crash.
- Accuracy: strong on everyday vocabulary (WER ~8–12% on clean speech); proper
  nouns and English loanwords still slip.

---

## Errors

Failures return a consistent JSON body, always with an actionable `hint` where one exists:

```json
{ "detail": "Cannot reach the Ollama daemon at http://localhost:11434.",
  "hint": "Start it with `ollama serve`, then confirm with `curl .../api/tags`." }
```

| Status | Meaning |
|---|---|
| `422` | Invalid request body (FastAPI validation). |
| `404` | Unknown session, or a model that isn't installed (hint names the `ollama pull`). |
| `502` | Ollama replied with an error, or returned malformed JSON for a structured endpoint. |
| `503` | Ollama daemon unreachable. |
| `504` | Generation exceeded the timeout. |

During streaming the HTTP status is already committed, so failures arrive as an
`{"type": "error"}` event instead — always handle that case.

A request that fails does **not** leave the student's message in the session history, so
retrying the same message is safe.

---

## Configuration

Copy `.env.example` to `.env` to override any of these:

| Variable | Default | Notes |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | |
| `OLLAMA_MODEL` | `gemma2:2b` | One model for every language. `qwen2.5:1.5b` is faster but can't do coherent Hindi/Marathi; a per-language split reloaded a model on every switch (slower on 4 GB). Any model from `ollama list`. |
| `OLLAMA_KEEP_ALIVE` | `-1` | How long Ollama keeps the model in RAM after a request. `-1` = never unload. Biggest felt-latency fix on 4 GB — the default unloads after 5 min idle and the reload is ~10-20 s. |
| `WARM_MODEL_ON_STARTUP` | `true` | On boot, the backend fires a 1-token generation (background task) to load the model into RAM, so the first student's first question doesn't pay the cold start. |
| `TEMPERATURE` | `0.7` | |
| `TEMPERATURE_NON_ENGLISH` | `0.6` | Slightly lower for non-English turns (less script drift); not lower, or a small model loops phrases. |
| `REPEAT_PENALTY` / `REPEAT_LAST_N` | `1.15` / `128` | Mild anti-repetition over Ollama's 1.1/64 defaults. Don't raise much — high values garble Devanagari. |
| `MAX_TOKENS` | `220` | Per-reply cap (`num_predict`). Low on purpose — a Socratic answer is 2-3 sentences, and it's the biggest CPU-latency lever (Hindi ≈ 2-4x tokens/word). |
| `NUM_CTX` | `3072` | Context window. Small = faster prompt processing on CPU. |
| `MAX_HISTORY_MESSAGES` | `10` | Messages replayed per turn. Short — each replayed turn is re-processed on CPU. |
| `SESSION_TTL_MINUTES` | `180` | Idle sessions are evicted. |
| `CORS_ORIGINS` | `*` | Comma-separated, or `*`. |
| `STT_MODEL_DIR` | `models/indicconformer` | IndicConformer model folder (relative to `apps/backend/`). |
| `STT_NUM_THREADS` | `2` | Threads for STT inference. |

---

## Known limitations

These are properties of a 1.5B model, not bugs in the API — worth knowing before the demo:

- **Factual accuracy is unreliable.** The model confidently produces wrong explanations
  (during testing it claimed "water is denser than ice" while explaining flotation). Fine
  for demonstrating the plumbing; don't put it in front of real students.
- **`style: "socratic"` is best-effort.** The model tends to lecture instead of asking
  questions. The backend detects this and re-asks once, which took adherence from 0/6 to
  3/6 in testing. `direct` and `exam_prep` are followed reliably.
  Streaming skips this check (the reply is already in flight), so socratic mode holds
  better on `/api/chat` than on `/api/chat/stream`.
- **Quiz distractors are sometimes weak** and the "correct" answer is occasionally
  arguable. `answer_index` itself is trustworthy: the model names the correct option as
  text and the server derives the index, because the model miscounts positions.
- **Grading is strict but sound.** `/api/tutor/evaluate` matched the expected verdict on
  5 of 6 hand-checked answers; the miss was a vague-but-not-wrong answer marked
  `incorrect` rather than `partially_correct`, so it errs toward harsh. It no longer
  endorses misconceptions — an earlier version scored "the moon pulls water into the sky"
  at 75/100 and invented supporting evidence for it. Two things make it hold: the schema
  decodes an internal `is_anything_wrong` boolean *before* the verdict, and the server
  reconciles the verdict with that boolean.
- **`feedback` is often written in the third person** ("The student's answer is...")
  rather than addressed to the student. Attempts to fix this in the prompt cost grading
  accuracy, so it was left alone — render it as teacher-facing notes, or post-process it.
- Sessions are **in-memory** — restarting the server clears them.

Moving to `qwen2.5:3b` or `7b` (same API, just change `OLLAMA_MODEL`) improves all of the
above at the cost of speed and RAM.

---

## Project layout

```
apps/backend/
  app/
    main.py                  FastAPI app, CORS, lifespan, error handlers
    config.py                Settings (env / .env)
    schemas.py               Request + response models = the API contract
    routers/
      health.py              /health, /api/models
      chat.py                /api/chat, /api/chat/stream
      sessions.py            /api/sessions/*
      tutor.py               /api/tutor/{explain,quiz,evaluate}
    services/
      ollama_client.py       Async Ollama HTTP wrapper + error translation
      sessions.py            In-memory conversation store (TTL + LRU)
      tutor.py               Prompts and JSON schemas for structured output
  smoke_test.py              End-to-end check of every endpoint
  run.sh                     Starts the server, bootstrapping the venv
apps/frontend/                Web client (other developers)
```

**Implementation note:** the structured endpoints constrain Ollama's decoder with a JSON
schema (`format`), rather than asking the model to "reply in JSON". On a 1.5B model that is
the difference between reliable objects and frequent parse failures.
