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
   Answer spoken aloud (Piper TTS) + shown in chat
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
| [`react-sts-hooks`](https://www.npmjs.com/package/react-sts-hooks) | `useSpeechToText` (Web Speech API wrapper) + `usePiper` (Piper neural TTS running in a Web Worker) |
| `onnxruntime-web` | Runs the Piper `.onnx` voice model in-browser. Required by the Piper worker but **not** bundled by `react-sts-hooks` itself — we vendor it in via `scripts/copy-ort-assets.mjs` (see §4) |
| Piper voice model (`en_US-amy-medium`) | The actual TTS voice — `.onnx` + `.json`, downloaded separately, not committed (large binary) |
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

**Text-to-speech:** fully offline once the model is cached. `usePiper` spins up a Web
Worker that:
1. Downloads the Piper voice model (`.onnx` + `.json`, ~60MB) and caches it in the
   browser's Cache Storage API (`piper-models-cache-v1`) — only re-downloaded if the
   cache is empty or gets purged.
2. Loads `onnxruntime-web` and runs the ONNX model entirely in-WASM to synthesize
   speech from text — no server round-trip.
3. Plays the resulting audio via the standard `Audio` element.

No network calls happen during actual TTS synthesis or playback — only during the
one-time model download.

## 4. Installation / Setup

**Prerequisites:** Node.js 18+, npm, and Google Chrome or Microsoft Edge installed.

### Quick start (one command)

From the repo root, on Windows:
```powershell
powershell -File scripts\setup.ps1
```

This runs every step below for you — `npm install` in both `apps/frontend` and
`apps/desktop`, creates `apps/frontend/.env` (mock mode on, so it works with no
backend), and downloads the Piper voice model files into
`apps/frontend/public/models/`. It's safe to re-run any time: each step checks first
and skips if it's already done, so re-running just fills in whatever's missing.

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

`npm install` triggers two setup steps automatically via `postinstall`:

1. `react-sts-hooks`'s own setup script — copies Piper's WASM worker files and
   downloads `piper_phonemize.data` (~18MB) into `public/piper-wasm/`.
   If it doesn't run (e.g. blocked by an install-script allowlist), run it by hand:
   ```bash
   npx react-sts-setup
   ```
2. Our own `scripts/copy-ort-assets.mjs` — copies `onnxruntime-web`'s runtime
   (`ort.min.js` + the wasm/mjs pair it needs, ~28MB) from `node_modules` into
   `public/`. Re-run manually any time with:
   ```bash
   node scripts/copy-ort-assets.mjs
   ```

**Voice model files (not included — must be added manually):**

Download `en_US-amy-medium.onnx` and `en_US-amy-medium.json` from
[Piper's voice samples](https://rhasspy.github.io/piper-samples/) (or directly from
the [`rhasspy/piper-voices`](https://huggingface.co/rhasspy/piper-voices) model repo
on Hugging Face — note the config there is named `<voice>.onnx.json`, rename it to
`<voice>.json`) and place both files in `apps/frontend/public/models/`.

**Environment config:**

```bash
cp .env.example .env
```

```ini
VITE_API_BASE_URL=http://localhost:8000       # your backend's URL
VITE_USE_MOCK_API=true                        # true = canned tutor replies, no backend needed
VITE_VOICE_MODEL_URL=/models/en_US-amy-medium.onnx
VITE_VOICE_CONFIG_URL=/models/en_US-amy-medium.json
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

## 7. Known Gaps

- **STT offline claim unverified** — see the caveat in §3; `processLocally` isn't set,
  so recognition may currently depend on network access.
- **Backend not implemented** — mock mode (§4) is the only working Q&A path today.
- **Class/subject selection** — built once, then removed for simplicity; static values
  are used instead. Revisit if per-class/subject content is needed.
