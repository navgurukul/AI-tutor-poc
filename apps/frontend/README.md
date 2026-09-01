# AI Tutor POC

## 1. Project Overview

A proof-of-concept offline AI tutor for low-spec devices (~4GB RAM target). A student
picks up a mic, asks a question out loud, and gets a spoken answer back — no internet
required for the voice pipeline itself.

Current flow:

```
App opens (borderless window)
        │
        ▼
   Tutor screen (Class 6 · Mathematics — static for now)
        │
        ▼
     🎤 Speak → on-device transcript
        │
        ▼
   Question sent to backend (POST /tutor/ask)
        │
        ▼
   Answer text comes back
        │
        ▼
   Answer spoken aloud (browser speech synthesis) + shown in chat
```

**Scope of this repo right now:** the frontend POC and a desktop launcher only. The
Python backend is not implemented here yet — see [§6](#6-backend-api-contract) for the
exact contract it needs to satisfy. Until then, the frontend runs against a built-in
mock (`VITE_USE_MOCK_API=true`).

Class/subject selection screens were built earlier and then intentionally removed to
simplify the flow — `App.tsx` currently passes static `Class 6 · Mathematics` values.
Easy to reinstate or swap for a different static pair later.

## 2. Tech Stack

| Piece | What / Why |
|---|---|
| React 19 + TypeScript + Vite | UI, build tooling, dev server with HMR |
| [`react-sts-hooks`](https://www.npmjs.com/package/react-sts-hooks) | `useSpeechToText` — a thin wrapper over the browser's Web Speech API, used for English STT |
| `src/hooks/useSpeechSynthesis.ts` | Answers are read aloud with the browser's built-in `window.speechSynthesis` (Web Speech API). No model, no download; uses the OS voices (local = offline). Replaced Piper — see §3 |
| `onnxruntime-web` (still a dep) | Was used by the old Piper worker. Currently unused by app code; kept so switching back is a one-commit revert. The `copy-ort-assets` postinstall and `public/` assets are likewise dormant |
| Hand-written CSS | No UI framework; light/dark theme via `prefers-color-scheme` |
| `apps/desktop/launch.mjs` | Plain Node script that opens the built frontend in a **borderless Chrome/Edge window** (`--app` mode) — deliberately not Electron, to stay light |
| Python backend (planned) | Not in this repo yet. Contract in §6 |

No routing library, no state management library, no component library — kept minimal
on purpose for the RAM budget.

## 3. How Offline STT + TTS Is Implemented

**Speech-to-text:** a small pluggable engine layer (`src/hooks/stt/`) picks the
recognizer per language, chosen in `src/config/languages.ts`:

| Language | Engine (`stt.engine`) | Where it runs |
| --- | --- | --- |
| English | `browser` | `useSpeechToText` from `react-sts-hooks` — the browser's Web Speech API, on-device, streaming, 1s silence auto-stop |
| Hindi, Gujarati, Kannada, Marathi | `indic` | the backend's `POST /api/stt` — sherpa-onnx + AI4Bharat's **IndicConformer** (one int8 multilingual model), fully offline, correct native script |

`useTutorSpeechToText(language)` mounts every engine hook, keeps the unselected
one dormant, and returns the active one's output as a single `TutorStt` shape;
nothing downstream branches on the engine. Adding a language is a row in
`languages.ts`; adding an engine is one hook + one `case`.

The `indic` path records a short clip in the browser (16 kHz mono WAV) and POSTs
it on mic release. IndicConformer is batch (no live partials), so decoding shows
as "Transcribing…" for ~1s (≈0.1× real-time). You can tap **Send** to stop and
submit early instead of waiting out the silence timeout (see §7).

> Chrome's `SpeechRecognition` streams audio to Google's servers for the Indic
> locales, which is why those go to the offline IndicConformer model on the
> backend. English on-device recognition works offline on Windows via the OS
> recognizer.
>
> One ~188 MB int8 model covers all four Indian languages (its native set is 8:
> Assamese, Bengali, Bodo, Gujarati, Hindi, Kannada, Kashmiri, Marathi). On
> everyday vocabulary it's strong; proper nouns and English loanwords still slip.
> `STT_MODEL_DIR` points at the model folder if you want to swap it.

**Text-to-speech:** `src/hooks/useSpeechSynthesis.ts`, a thin wrapper over the
browser's built-in `window.speechSynthesis`. No model files, no download, no
warm-up. `useTutorSession` peels each finished sentence off the token stream
(`drainSentences`) and calls `speak()`; the browser's own queue plays them
back-to-back, gaplessly, faster than real time — first audio is well under a
second even on the ~4 GB target.

Voice selection: it prefers a **local** (offline) voice whose language matches the
selected tutor language, so English uses an English voice and Hindi/Marathi use a
`hi-IN` / `mr-IN` voice **if the OS has one**. On Windows that means the language's
speech pack (Settings → Time & Language → Speech). When no matching voice exists
the hook still speaks (wrong-language voice) and sets `voiceMissing`, which the UI
surfaces as a hint.

> Why not Piper: Piper's voice is English-only (it can't pronounce Hindi/Marathi
> at all) and its WASM synthesis lags real time on a 4 GB CPU (~3.5–4 s to first
> audio, gaps between sentences). The browser synthesizer is offline via the OS
> voices, multi-language, and near-instant. Trade-off: the system voice is less
> natural. Piper wiring was removed but its npm dep / `public/` assets are left in
> place for an easy revert.

## 4. Installation / Setup

**Prerequisites:** Node.js 18+, npm, and Google Chrome or Microsoft Edge installed.

### Quick start (one command)

From the repo root, on Windows:
```powershell
powershell -File scripts\setup.ps1
```

This runs every step below for you — `npm install` in both `apps/frontend` and
`apps/desktop` and creates `apps/frontend/.env` (mock mode on, so it works with no
backend). It's safe to re-run any time: each step checks first and skips if it's
already done, so re-running just fills in whatever's missing. (It still fetches the
old Piper voice files; harmless — nothing uses them now.)

Once it finishes:
```bash
cd apps/desktop
npm start
```
That opens the AI Tutor in a borderless window — see [§5](#5-running--all-commands)
for what this does under the hood.

To rebuild after changing code, without going through the full launcher flow:
```powershell
powershell -File scripts\build.ps1
```

Not on Windows, or want to see what the script automates? The rest of this section
walks through the same steps by hand.

### Manual setup

```bash
cd apps/frontend
npm install
```

`npm install` runs `scripts/copy-ort-assets.mjs` via `postinstall`. It copied the
old Piper/onnxruntime runtime into `public/`; nothing uses those files now, but the
step is left in so reverting to Piper is a one-commit change. Speech recognition
(English) and synthesis both use the browser's Web Speech API and need no assets.

**Voice model files:** none. Text-to-speech uses the browser's `speechSynthesis`
and the OS voices. For offline Hindi/Marathi audio, install that language's speech
pack in Windows (Settings → Time & Language → Speech); English works out of the box.

**Environment config:**

```bash
cp .env.example .env
```

```ini
VITE_API_BASE_URL=http://localhost:8000       # your backend's URL
VITE_USE_MOCK_API=true                        # true = canned tutor replies, no backend needed
```

Set `VITE_USE_MOCK_API=false` once the real backend from §6 is up and reachable at
`VITE_API_BASE_URL`.

## 5. Running — All Commands

**Frontend in a normal browser tab (hot reload, for active development):**
```bash
cd apps/frontend
npm run dev
```
Open the URL Vite prints (defaults to `http://localhost:5173`).

**Production build:**
```bash
cd apps/frontend
npm run build     # type-checks (tsc -b) + builds to apps/frontend/dist
npm run preview   # serves dist/ locally, to sanity-check the production build
```

**Desktop app — borderless window (this is "run it like a desktop app"):**
```bash
cd apps/desktop
npm start         # production: builds the frontend if needed, serves dist/ offline, opens a borderless window
npm run dev       # development: same borderless window, but backed by the Vite dev server (HMR)
```

`npm start` in `apps/desktop`:
- Auto-detects an installed Chrome or Edge (standard Windows install paths).
- Opens it with `--app=<url>` — no address bar, no tabs, just the app.
- Uses a fresh, isolated browser profile (`--user-data-dir`), so it won't touch your
  normal browser's tabs, history, or login.
- Fully offline after the first build + model download — the only network calls at
  runtime go to your configured backend (or none at all, in mock mode).

**Lint:**
```bash
npm run lint      # oxlint
```

## 6. Backend API Contract

The frontend calls exactly one endpoint. This is what your Python backend needs to
implement to receive real questions instead of the mock.

### `POST {VITE_API_BASE_URL}/tutor/ask`

**Headers:** `Content-Type: application/json`

**Request body:**
```json
{
  "classId": "class-6",
  "subjectId": "math",
  "question": "What is 7 times 8?"
}
```

| Field | Type | Notes |
|---|---|---|
| `classId` | `string` | Currently a static placeholder (`"class-6"`) set in `App.tsx`, since class-selection UI was removed. Will vary once that UI comes back. |
| `subjectId` | `string` | Same — currently static (`"math"`). |
| `question` | `string` | The final transcript captured from the student's speech via the Web Speech API, sent verbatim — not cleaned, punctuated, or translated by the frontend. |

**Expected response — `200 OK`:**
```json
{
  "answer": "Fifty-six."
}
```

| Field | Type | Notes |
|---|---|---|
| `answer` | `string` | Plain text only — no markdown/HTML. This is spoken aloud verbatim by Piper TTS *and* shown as a chat bubble, so avoid symbols/formatting the voice model can't pronounce sensibly (e.g. write "56" or "fifty-six", not `**56**`). |

**Errors:** any non-2xx response is shown to the user as `"{status} {statusText}: {body}"`.
No special error JSON shape is required — just return a short, human-readable message
in the response body if you can.

**Reference types** (`src/types/index.ts`):
```ts
interface AskTutorRequest {
  classId: string;
  subjectId: string;
  question: string;
}

interface AskTutorResponse {
  answer: string;
}
```

## 7. Latency & UX Changes

The tutor has to feel fast on a slow device. What was added:

### Model warm-up (two stages)
1. **Backend startup** — `WARM_MODEL_ON_STARTUP` (`app/main.py`): the backend fires a
   1-token generation in a background task on boot, so the model is loaded into RAM
   before the first browser ever connects. With `OLLAMA_KEEP_ALIVE=-1` it then stays
   resident. This moves the ~10-20 s cold start onto server boot.
2. **Page load** — `warmupTutor()` in `services/api.ts` fires one throwaway
   `POST /api/chat` (`max_tokens: 1`, same profile incl. socratic style) when the tutor
   screen mounts. The model is already resident from stage 1, so this just makes Ollama
   cache the **system-prompt prefix** the first real question reuses. The backend skips
   the socratic re-ask for a 1-token reply. The mic stays disabled (`isModelWarm`) until
   this settles — now a second or two, not the full cold load.

### Streaming answer + sentence-by-sentence speech
`POST /api/chat/stream` (SSE) delivers the reply token by token. The bubble text updates
on every token — full speed, never held back. `drainSentences()` peels off each complete
sentence as it finishes and calls `speak()`, so the voice is reading sentence 1 while the
model is still writing sentence 2. The browser's speech queue plays queued phrases
gaplessly and faster than real time, so first audio lands well under a second with no
opener trick or pre-buffer needed.

### One model, tuned for latency
`gemma2:2b` for every language (`OLLAMA_MODEL`). `qwen2.5:1.5b` is faster but its Hindi is
unusable (repetition loops or word salad — no decoding setting in between), and a
per-language split was tried and reverted: on a 4 GB box every language switch reloaded a
model, which cost more than it saved. To keep it responsive on CPU the backend also runs
a low `MAX_TOKENS` (220 — a Socratic answer is 2-3 sentences), a small `NUM_CTX` (3072)
and short history (`MAX_HISTORY_MESSAGES` 10), nudges the temperature down for non-English
(`TEMPERATURE_NON_ENGLISH` 0.6) with a mild `REPEAT_PENALTY` 1.15 / `REPEAT_LAST_N` 128,
and the system prompt names the Devanagari script and carries one short Hindi worked
example. Even so, gemma2:2b on a 4 GB CPU is the accuracy/speed ceiling here — a bigger or
Indic-specialised model, or a LAN Ollama host (`VITE_API_BASE_URL` → another box), is the
real fix if Hindi needs to be better or faster.

### Live transcript in the chat
The recognized speech shows straight in the chat as a faint user bubble — live word by
word for English, and once decoded (~1 s) for the offline Indic engine — then becomes the
real message. There's no separate text box. The mic button reads **Send** while listening
(tap to submit now); otherwise the 1 s silence timeout closes the mic and submits on its
own.

### "Stop audio" stops only the audio
It used to also abort the LLM stream. Now it silences the voice and blocks the remaining
sentences from being spoken, but the written answer finishes streaming into the bubble.

### Stable message ids
`nextId()` uses `crypto.randomUUID()` instead of a module-level counter. The counter reset
on every HMR reload while the message list survived, colliding ids so a streamed reply
rendered into an earlier bubble.

### Layout
`.app-shell` is pinned to the viewport and `.chat-log` gets `min-height: 0`, so a long
thread scrolls inside the chat area instead of pushing the mic controls off-screen.

## 8. Known Gaps

- **STT offline claim unverified** — see the caveat in §3; `processLocally` isn't set,
  so recognition may currently depend on network access.
- **Backend contract (§6) is stale** — it describes an unbuilt `POST /tutor/ask`. The
  backend exists now; the real contract is `POST /api/chat/stream` (SSE) — see
  `apps/backend/README.md` and `src/services/api.ts`.
- **Browser TTS voice quality / availability** — answers use `window.speechSynthesis`
  (first audio <1 s, gapless). The system voice is less natural than Piper's, and an
  *offline* Hindi/Marathi voice only exists if the OS speech pack is installed —
  otherwise it falls back to a wrong-language voice and shows a `voiceMissing` hint.
  Piper wiring was removed; its npm dep and `public/` assets remain for a quick revert.
- **Class/subject selection** — built once, then removed for simplicity; static values
  are used instead. Revisit if per-class/subject content is needed.
