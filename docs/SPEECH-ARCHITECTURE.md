# AI Tutor — Speech Architecture (branch `aibharat-stt`)

A plain-English walkthrough of how the offline voice tutor works: which models,
which files, how the frontend and backend talk to each other, and the trade-offs
behind each choice. Read top to bottom and you can explain the whole system.

---

## 1. The big picture

The app is a voice tutor that runs **on the user's own machine** — no cloud, no
internet needed at question time. One turn looks like this:

```
  You speak  ─►  STT  ─►  LLM  ─►  TTS  ─►  Speaker
             (speech    (the      (text     (audio
              to text)  "brain")  to speech) out)
```

- **STT** = Speech‑To‑Text. Turns your spoken question into written text.
- **LLM** = the language model. Reads the text, writes the answer.
- **TTS** = Text‑To‑Speech. Reads the answer out loud.

Each of the three has **two paths** depending on the language:

| Stage | English | Hindi / Marathi |
|---|---|---|
| STT | Browser's built‑in speech recogniser | Our backend + an Indian‑language model |
| LLM | Same model for every language (`gemma2:2b`) | Same |
| TTS | Browser's built‑in OS voice | Our backend + a Piper voice (Hindi only) |

The reason for two paths: the browser already does English well and instantly,
but it can't do Indian languages offline. So for Indian languages we run our own
models on the backend.

---

## 2. The three models (what and why)

### 2a. STT model — AI4Bharat **IndicConformer‑600M**

- **What it is:** a 600‑million‑parameter speech recognition model from AI4Bharat
  (IIT Madras), trained on 22 Indian languages. We use the **CTC** variant.
- **How we run it:** through **sherpa‑onnx** — a small, pre‑built speech library
  (no compiler needed). File on disk: `apps/backend/models/indicconformer/model.onnx`
  (~470 MB) + `tokens.txt`.
- **Format:** `fp32` (full precision).
- **Only used for Hindi and Marathi.** English speech never reaches the backend.

**Trade‑offs:**

| Choice | Why |
|---|---|
| fp32 instead of int8 (smaller) | int8 roughly **doubles the error rate** on Hindi (~16% → ~30%). The 280 MB saved isn't worth worse transcripts. |
| This specific export (`meetsync/...`) | It's the only ready‑made sherpa‑compatible IndicConformer. Verified for 8 languages (Hindi, Marathi, Bengali, Gujarati, Kannada, Assamese, Bodo, Kashmiri). **Tamil & Telugu are not covered yet** — they'd need a different export. |
| Batch, not streaming | IndicConformer is an "offline" model — it can't emit words as you speak like the browser does. We fake a live feel (see §4) but the accurate transcript only comes after you stop talking (~1 second). |

### 2b. LLM — Google **Gemma 2 (2B)** via Ollama

- **What it is:** a 2‑billion‑parameter language model, running locally through
  **Ollama** (a local model server). One model handles **every** language.
- **Why not the smaller `qwen2.5:1.5b`:** the 1.5B model **cannot write coherent
  Hindi** — it loops or produces word salad. 2B is the smallest that works.
- **The tutor's personality** lives in a system prompt (`app/services/tutor.py`):
  "explain the concept with an example, like a patient tutor for a school
  student, no emojis, plain prose." For Hindi it also repeats "write your entire
  answer in Devanagari script" and includes a worked example.

**Trade‑offs:**

| Choice | Why / cost |
|---|---|
| 2B model on a ~4 GB CPU box | It's **slow**: first word ~3–5 s when warm, ~15 s cold; a full Hindi answer ~5–15 s. Hindi costs 2–4× more "tokens" (word pieces) than English, so it's slower still. |
| `MAX_TOKENS = 200` | A tutor answer is 2-3 short sentences + an example; a low cap is the biggest CPU-latency lever. |
| `OLLAMA_KEEP_ALIVE = -1` | Tells Ollama to never unload the model between questions (otherwise it reloads after 5 min idle = ~15 s hit). |
| Warm‑up on page load | The app fires one throwaway question so the model and the Hindi prompt are "hot" before the student asks for real. |
| Accuracy | A 2B model **gets facts wrong sometimes**. Fine for a demo, not for unsupervised study. |

### 2c. TTS model — **Piper `hi_IN-priyamvada`** (Hindi, female) via sherpa‑onnx

- **What it is:** a Piper VITS voice — small, fast, natural‑ish. `priyamvada` is a
  **female** Hindi voice. File: `apps/backend/models/tts/vits-piper-hi_IN-priyamvada-medium/`
  (~63 MB: the `.onnx` voice + `tokens.txt` + `espeak-ng-data/` for pronunciation).
- **How we run it:** through the **same sherpa‑onnx** already installed for STT —
  **no new dependency**.
- **English** uses the browser's own OS voice instead (instant, nothing to
  install on our side).
- **Marathi** has **no Piper voice** — it falls back to the browser OS voice, so
  it only speaks if Windows has a Marathi speech pack installed.

**Trade‑offs — why Piper and not the alternatives:**

| Option | Verdict |
|---|---|
| **Browser MMS‑TTS** (transformers.js, runs in the browser) | Tried and **rejected**: ~15 seconds to speak one sentence on this CPU, and the Hindi voice is male and robotic. Neural TTS in the browser is simply too slow on a 4 GB box. |
| **Indic Parler‑TTS** | Great coverage (21 languages) but **0.9 B params and autoregressive** — far too big and slow for this hardware. |
| **IndicVoice‑82M** | Nicely small and fast, but **only Hindi/Bengali** — no Marathi/Tamil/Telugu. |
| **Piper (chosen)** | ~0.7 s per sentence on CPU, female Hindi voice, reuses sherpa‑onnx. **Downside: Piper only has Hindi + English** among our languages — no Marathi/Tamil/Telugu voice exists. |
| **MMS‑TTS on the backend** (future) | Would cover Marathi/Tamil/Telugu/Bengali, but the voices are male and flat. A backend option for later. |

---

## 3. Every file, and how it connects

### Frontend (`apps/frontend/src/`)

| File | Plain‑English job |
|---|---|
| `App.tsx` | Holds which language is selected; saves it to the browser (`localStorage["tutor.language"]`) so it's remembered next time. |
| `config/languages.ts` | The **list of languages** in the dropdown (English, Hindi, Marathi). Each row says which STT engine and whether TTS goes to the backend. |
| `components/LanguageSelect.tsx` | The language dropdown in the header. |
| `pages/TutorPage.tsx` | The whole screen: header, chat log, mic button, and the "Preparing…" / "Downloading…" progress bars. |
| `components/MicButton.tsx` | The Speak / Send button. Just a button — no logic. |
| `components/ChatBubble.tsx`, `ErrorBanner.tsx`, `VoiceToggle.tsx`, `StopSpeechButton.tsx` | Small UI pieces. |
| **`hooks/useTutorSession.ts`** | **The orchestrator.** Wires STT + LLM + TTS together, runs the turn state machine (idle → listening → thinking → speaking), splits the streaming answer into sentences (`drainSentences`), strips markdown before speaking (`stripForSpeech`), and prints all the `[timing]` logs. If you read one file, read this one. |
| `hooks/stt/types.ts` | The **contract** every STT engine must fulfil (`TutorStt`): `startListening`, `stopListening`, `transcript`, `isListening`, etc. So the rest of the app never cares which engine is running. |
| `hooks/stt/useTutorSpeechToText.ts` | The **STT router** — picks browser vs backend based on the language. |
| `hooks/stt/useBrowserSpeechToText.ts` | English STT — thin wrapper over the browser's Web Speech API. |
| `hooks/stt/useIndicSpeechToText.ts` | Hindi/Marathi STT — records the mic, runs a tiny voice‑activity detector, POSTs audio to `/api/stt`, shows a live rough transcript, does a clean final decode when you pause. |
| `hooks/tts/useTutorTts.ts` | The **TTS router** — English → browser voice, Hindi → backend. |
| `hooks/tts/useBackendTts.ts` | Hindi TTS — POSTs each sentence to `/api/tts`, gets a WAV back, and plays the sentences **back‑to‑back with no gaps** using Web Audio. Also unlocks audio on the first mic tap (browsers block audio that isn't started by a click). |
| `hooks/useSpeechSynthesis.ts` | English TTS — the browser's built‑in `speechSynthesis`. |
| `services/api.ts` | All the HTTP calls to the backend: `askTutorStream` (the streaming chat), `warmupTutor` (the throwaway warm‑up question), and `API_BASE_URL`. |

### Backend (`apps/backend/app/`)

| File | Plain‑English job |
|---|---|
| `main.py` | Starts the FastAPI server. On boot it **warms up** the LLM, the STT model, and the TTS voice in the background so the first real request is fast. Registers all the routes. |
| `config.py` | Every setting in one place (model names, thread counts, token limits…). Any of them can be overridden in `apps/backend/.env`. |
| `schemas.py` | The shapes of every request and response — this **is** the API contract. |
| `routers/chat.py` | `POST /api/chat` and `POST /api/chat/stream` — send a message, get the tutor's reply (streamed word by word for the UI). |
| `routers/stt.py` | `GET /api/stt` (is the model ready?) and `POST /api/stt` (send a WAV clip, get `{ "text": "…" }`). |
| `routers/tts.py` | `GET /api/tts` (is the voice ready?) and `POST /api/tts` (send `{ "text": "…" }`, get a WAV back). |
| `routers/health.py`, `sessions.py`, `tutor.py` | Health check, conversation history, and structured tutor tasks (quiz / explain / grade). |
| `services/ollama_client.py` | Talks to Ollama over HTTP; turns its errors into friendly messages. |
| `services/sessions.py` | Remembers the conversation so far, in memory (cleared on restart). |
| `services/tutor.py` | Builds the **system prompt** — the tutor's personality and language rules. |
| `services/stt.py` | Loads IndicConformer via sherpa‑onnx once, then turns a WAV into Hindi/Marathi text. |
| `services/tts.py` | Loads the Piper voice via sherpa‑onnx once, then turns text into a WAV. |

### Where models live (not in git — downloaded by setup)

```
apps/backend/models/
  indicconformer/model.onnx , tokens.txt          ← STT
  tts/vits-piper-hi_IN-priyamvada-medium/...       ← Hindi TTS voice
```

### Scripts

- `scripts/setup.ps1` — one‑time: installs dependencies and **downloads the model
  files** (IndicConformer ~470 MB, Piper voice ~63 MB).
- `scripts/start.ps1` — starts the backend, then opens the app.

---

## 4. One Hindi turn, step by step

1. **Pick the language.** You choose *हिन्दी* in the dropdown.
   `App.tsx` saves it and passes it to `useTutorSession`.

2. **Warm‑up (automatic).** The app quietly sends one throwaway question to the
   LLM so Gemma loads the Hindi system prompt into memory, and pings
   `GET /api/stt` and `GET /api/tts` so those models load too. While this
   happens the mic is disabled and the header says *"Preparing the हिन्दी
   tutor…"*.

3. **Tap Speak.** `startTurn()` runs. It first calls `primeAudio()` — this is
   the one moment we're allowed to start the audio system (browsers only let
   audio begin on a real click). Then the mic opens.

4. **You talk.** `useIndicSpeechToText` records your voice as 16 kHz audio and
   watches the volume. Every ~1.1 seconds it sends the audio‑so‑far to
   `POST /api/stt` and shows a rough **live transcript** in a faint grey bubble —
   so it feels responsive even though the model is "batch".

5. **You pause.** After ~1.1 s of silence (or you tap *Send*), it sends the
   whole clip one last time. `app/services/stt.py` runs it through
   IndicConformer and returns the clean Devanagari text.

6. **Ask the LLM.** `useTutorSession` sees the final text and immediately calls
   `askTutorStream(...)` → `POST /api/chat/stream`, including
   `profile.language = "Hindi"`.

7. **The tutor writes.** `routers/chat.py` builds the message list
   (system prompt from `tutor.py` + recent history) and streams Gemma's answer
   back one token at a time over SSE.

8. **Show it live.** The frontend appends every token to the tutor's chat bubble
   as it arrives, so you watch the answer being written.

9. **Speak it, sentence by sentence.** As tokens arrive, `drainSentences` pulls
   off each *complete* Hindi sentence (they end with the danda "।"). Each
   sentence is cleaned by `stripForSpeech` (removes `*`, `#`, backticks so the
   voice doesn't say "तारांकन") and handed to `useBackendTts.speak()`.

10. **Backend synthesises.** `speak()` POSTs the sentence to `/api/tts`;
    `services/tts.py` runs Piper and returns a WAV (~0.7 s).

11. **Play gaplessly.** `useBackendTts` decodes each WAV and plays the sentences
    **in order, back‑to‑back**. Sentence 1 starts playing while Gemma is still
    writing sentence 3.

12. **Done.** The turn ends when the token stream closes and the last sentence
    finishes playing. The state goes back to *idle*.

An **English** turn is the same shape but simpler: step 4–5 use the browser's
own recogniser (live, word‑by‑word, no `/api/stt`), and steps 9–11 use the
browser's own voice (no `/api/tts`).

---

## 5. Known limitations & trade‑offs (the honest list)

| Area | Limitation | Why / possible fix |
|---|---|---|
| **Speed** | Cold first question ~15–17 s; warm ~3–5 s to first word; full Hindi answer ~5–15 s. | It's Gemma 2 (2B) decoding on a ~4 GB CPU. Hindi = 2–4× the tokens. Fixes: `OLLAMA_NUM_PARALLEL=1` on the Ollama server (removes the cold spike), a smaller/faster model, or point `VITE_API_BASE_URL` at a stronger machine. |
| **Gaps between spoken sentences** | Sentence 1 plays, then a pause, then sentence 2. | The pause is Gemma writing the next sentence, **not** the TTS (Piper is ~0.7 s). We merge very short sentences (`MIN_SPEECH_CHARS = 60`) so the first chunk is longer and hides the gap. Can't remove it without a faster LLM. |
| **STT languages** | Only Hindi & Marathi are wired. Tamil/Telugu need a different IndicConformer export. | The current model file covers 8 Indic languages; ta/te aren't in it. |
| **STT is batch** | Hindi transcript appears ~1 s after you stop, not live word‑by‑word like English. | IndicConformer is an offline model. The live grey bubble is a re‑decode trick, not true streaming. |
| **TTS languages** | Only **Hindi** has a real offline voice (Piper). Marathi falls back to the OS voice. | Piper has no Marathi/Tamil/Telugu voice. Backend MMS‑TTS could fill the gap (male, flatter). |
| **English offline** | The browser recogniser streams audio to Google in Chrome. | Not truly offline for English STT. Edge does more on‑device. |
| **LLM accuracy** | Gemma 2 (2B) is confidently wrong sometimes; its Hindi is grammatical but shallow. | Property of a 2B model. A bigger model needs more RAM. |
| **Voice needs a click** | The MMS/Piper audio can't start on its own. | Handled: `primeAudio()` on the mic tap. |
| **Sessions are in memory** | Restarting the backend clears the conversation. | Fine for a POC. |

---

## 6. Quick reference — who calls whom

```
TutorPage.tsx
   └─ useTutorSession.ts  ◄─ the orchestrator
        ├─ useTutorSpeechToText.ts ─┬─ useBrowserSpeechToText.ts ──► browser Web Speech API
        │                           └─ useIndicSpeechToText.ts ────► POST /api/stt ──► services/stt.py ──► sherpa-onnx + IndicConformer
        ├─ services/api.ts .askTutorStream ─────────────────────────► POST /api/chat/stream ──► routers/chat.py ──► ollama_client.py ──► Ollama (gemma2:2b)
        │                                                                                         └─ services/tutor.py (system prompt)
        └─ useTutorTts.ts ─────────┬─ useSpeechSynthesis.ts ────────► browser OS voice
                                   └─ useBackendTts.ts ─────────────► POST /api/tts ──► services/tts.py ──► sherpa-onnx + Piper voice
```
