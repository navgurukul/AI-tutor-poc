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
   Answer streams back token by token
        │
        ▼
   Text fills the chat bubble live; each finished sentence is
   spoken by the browser's built-in speech synthesis
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
| [`react-sts-hooks`](https://www.npmjs.com/package/react-sts-hooks) | `useSpeechToText` only — a thin wrapper over the browser's `SpeechRecognition`. (`usePiper` from the same package is no longer used — see §3.) |
| `useSpeechSynthesis` (`src/hooks/`) | ~50-line wrapper over the browser's built-in `window.speechSynthesis`. Speaks the answer a sentence at a time; the OS synthesizes faster than real time, so playback is gapless. Replaced WASM Piper. |
| Hand-written CSS | No UI framework; light/dark theme via `prefers-color-scheme` |
| `apps/desktop/launch.mjs` | Plain Node script that opens the built frontend in a **borderless Chrome/Edge window** (`--app` mode) — deliberately not Electron, to stay light |
| Python backend (planned) | Not in this repo yet. Contract in §6 |

No routing library, no state management library, no component library — kept minimal
on purpose for the RAM budget.

## 3. How Offline STT + TTS Is Implemented

**Speech-to-text:** `useSpeechToText` wraps the browser's native Web Speech API
(`SpeechRecognition`), with a configurable silence timeout (1.5s) that auto-stops
listening once you go quiet.

> ⚠️ **Caveat to verify before calling this "fully offline":** Chrome's
> `SpeechRecognition` streams audio to Google's servers by **default**. On-device
> recognition requires explicitly setting a `processLocally: true` flag when creating
> the recognizer (undocumented on MDN, discovered while reviewing a sibling
> offline-STT test project). `react-sts-hooks` does **not** set this flag internally.
> As currently wired, STT likely requires network connectivity. This needs to be
> patched (or upstreamed to the package) before the "offline" claim is accurate.

**Text-to-speech:** the browser's built-in `window.speechSynthesis` (`useSpeechSynthesis`
in `src/hooks/`). As the answer streams in, each completed sentence is queued with
`speechSynthesis.speak(...)`; the browser plays queued utterances back-to-back. On
Windows/macOS the voices are local (SAPI / AVSpeechSynthesis), so it works offline and
needs no download.

Why not Piper (`usePiper`)? Piper runs a ~25 M-parameter neural vocoder in single-threaded
WASM. On the ~4 GB target device that synthesizes *slower than real time* (~1.5 s fixed
overhead + ~60 ms/char), so playback repeatedly caught up to the synthesizer and stuttered
between sentences, and first audio landed ~5–7 s in. `speechSynthesis` synthesizes faster
than it speaks, so first audio is under a second and there are no gaps. The trade is a
less natural system voice. The Piper code path is still in `react-sts-hooks` if a nicer
voice is ever worth the latency — re-add `usePiper` and the assets in §4.

## 4. Installation / Setup

**Prerequisites:** Node.js 18+, npm, and Google Chrome or Microsoft Edge installed.

### Quick start (one command)

From the repo root, on Windows:
```powershell
powershell -File scripts\setup.ps1
```

This runs every step below for you — `npm install` in both `apps/frontend` and
`apps/desktop`, and creates `apps/frontend/.env` (mock mode on, so it works with no
backend). It's safe to re-run any time: each step checks first and skips if it's already
done, so re-running just fills in whatever's missing.

> The script still fetches the old Piper voice model + WASM assets (~110 MB into
> `public/`). Nothing loads them any more (see §3); they're harmless dead weight until
> that step is trimmed.

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

Text-to-speech now uses the browser's built-in `speechSynthesis`, so there is **no
voice model, WASM runtime, or phonemizer to download** — `npm install` is all the
frontend needs. (`npm install` still runs `react-sts-hooks`'s `postinstall`, which
copies Piper worker assets into `public/piper-wasm/`; they're unused now.)

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
- Fully offline after the first build — the only network calls at runtime go to your
  configured backend (or none at all, in mock mode).

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
| `answer` | `string` | Plain text only — no markdown/HTML. It's spoken aloud verbatim by the browser's speech synthesis *and* shown as a chat bubble, so avoid symbols/formatting a voice can't pronounce sensibly (e.g. write "56" or "fifty-six", not `**56**`). |

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

## 7. Latency Work — What Changed & Why

The whole point of this POC is a fast spoken answer on a slow device. These are the
optimizations, in the order they matter, and what each buys.

### Streaming, not buffering
`POST /api/chat/stream` (SSE) delivers the answer token by token. The bubble text
updates on every token; complete sentences are handed to the speech engine as they
arrive. Nothing waits for the full answer. This is the single biggest win — a buffered
1.5 B-model reply feels slow, a streamed one feels instant.

### Model warm-up on page load — `warmupTutor()` in `services/api.ts`
The moment the tutor screen mounts, the frontend fires one throwaway
`POST /api/chat` (`max_tokens: 1`, with the session profile) and discards the reply.
That:
- pulls `qwen2.5:1.5b` into Ollama's memory (~10 s cold-start, weights off disk) while
  the student is still reading the screen, instead of on their first question;
- makes Ollama cache the **system-prompt prefix**, so the first real question only has
  to process the question itself.

Measured on this hardware: first question **~3.3 s → ~1.1 s**. No dedicated backend
endpoint — it's just a normal chat call. Cost: one throwaway session per page load,
evicted by TTL/LRU. The mic stays disabled (`isModelWarm`) until this settles.

### Browser speech synthesis instead of Piper — `hooks/useSpeechSynthesis.ts`
See §3. Piper's WASM neural TTS synthesizes slower than real time on the ~4 GB target,
so audio stuttered and first sound was 5–7 s in. `window.speechSynthesis` synthesizes
faster than it speaks: **first audio < 1 s, no gaps**, still offline. Removed with it:
the ~63 MB voice model, ~28 MB ONNX runtime, ~18 MB phonemizer, the Piper Web Worker,
and the audio-interceptor that existed only to stop Piper mid-utterance. Bundle
−5 KB gzip; page no longer fetches ~110 MB of assets.

### Sentence-at-a-time playback — `drainSentences()` in `hooks/useTutorSession.ts`
Tokens are buffered until a sentence boundary (terminator + whitespace, so "3.14"
stays intact), then that sentence is queued to speak. Fragments under 12 chars merge
into the next sentence. The browser plays queued sentences gaplessly, so the voice
tracks the streaming text closely without any explicit sync logic.

### "Send" button — `finishTurn()` + `MicButton`
While listening, the mic button reads **Send** and submits the captured transcript
immediately, instead of forcing a wait for the 1 s silence timeout (which is still the
fallback if you don't tap).

### Stable message ids — `nextId()`
`crypto.randomUUID()` instead of a module-level counter. The counter reset on every
HMR reload while the message list survived, colliding ids so a streamed reply
rendered into an earlier bubble.

### Tried and reverted
- **Multi-threaded ONNX** (COOP/COEP + `numThreads > 1` in the Piper worker) — thread
  pool overhead made it *worse* on this CPU.
- **`en_US-amy-low`** — same 63 MB network as `-medium` for this voice; no speed gain.
  No English Piper `x_low` exists.
- **Pacing on-screen text to playback** (`currentlyPlayingIndex`) — made the text
  crawl sluggishly to match choppy audio; not worth it once audio was smooth.

## 8. Known Gaps

- **STT offline claim unverified** — see the caveat in §3; `processLocally` isn't set,
  so recognition may currently depend on network access.
- **Backend contract section (§6) is stale** — it describes an unbuilt `POST /tutor/ask`.
  The backend exists now; the real contract is `POST /api/chat/stream` (SSE) — see
  `apps/backend/README.md` and `src/services/api.ts`.
- **Piper assets still downloaded by `setup.ps1`** — ~110 MB fetched into `public/` and
  copied into `dist/`, loaded by nothing. Trim the model-download + `react-sts-setup`
  steps, and the `onnxruntime-web` dependency, when convenient.
- **Class/subject selection** — built once, then removed for simplicity; static values
  are used instead. Revisit if per-class/subject content is needed.
