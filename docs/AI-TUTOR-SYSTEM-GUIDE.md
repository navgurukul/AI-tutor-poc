# Offline AI Tutor — System Guide

Everything about how the app works: architecture, speech-to-text, the textbook search (RAG), the
LLM and its cache, latency, every setting, worked examples, what we measured, what we chose,
pitfalls, and how it scales.

- Branch `mintplex-piper`, state of **2026-09-11** (changes since commit `f9f16ad` are not committed yet).
- Per-experiment detail (tried / failed / passed): [EXPERIMENT-LOG.md](EXPERIMENT-LOG.md).
- [SPEECH-ARCHITECTURE.md](SPEECH-ARCHITECTURE.md) is an older document from before English STT and
  all TTS moved to the backend; where the two disagree, this guide is current.

**How to read the numbers.** "Measured" means taken on the dev laptop with the in-app timing panel,
the backend log, or an A/B script. "Estimate" means calculated from measured rates, not timed end to
end. This laptop swings up to **2.4×** on identical work with temperature, so treat single readings
as ranges.

---

## Contents

1. [What the app is](#1-what-the-app-is)
2. [Hardware and hard constraints](#2-hardware-and-hard-constraints)
3. [Architecture](#3-architecture)
4. [Models and libraries — what and why](#4-models-and-libraries--what-and-why)
5. [Speech-to-text (STT)](#5-speech-to-text-stt)
6. [The textbook library — upload and ingestion](#6-the-textbook-library--upload-and-ingestion)
7. [Retrieval — how a question finds its passage](#7-retrieval--how-a-question-finds-its-passage)
8. [The LLM — prompt layout, prefill, decode](#8-the-llm--prompt-layout-prefill-decode)
9. [The cache — why turns are fast](#9-the-cache--why-turns-are-fast)
10. [Worked example — a lesson, call by call](#10-worked-example--a-lesson-call-by-call)
11. [Text-to-speech (TTS)](#11-text-to-speech-tts)
12. [Latency — where every second goes](#12-latency--where-every-second-goes)
13. [Accuracy — groundedness and citations](#13-accuracy--groundedness-and-citations)
14. [Every parameter](#14-every-parameter)
15. [What we checked and what we chose](#15-what-we-checked-and-what-we-chose)
16. [What improved, and by how much](#16-what-improved-and-by-how-much)
17. [Pitfalls](#17-pitfalls)
18. [Scale](#18-scale)
19. [Where we are, and what we can use next](#19-where-we-are-and-what-we-can-use-next)
20. [Running it, and where to look](#20-running-it-and-where-to-look)

---

## 1. What the app is

A **voice tutor** for school students in **Hindi, Marathi and English** that runs entirely on one
laptop, **offline at question time**. The student picks a language, class and subject, asks a
question out loud, and hears an answer grounded in their own uploaded textbook, with the page it
came from.

```
  Student speaks ─► STT ─► textbook search (RAG) ─► LLM ─► TTS ─► Student hears
                  (speech    (find the right page)   (write    (speak the
                   to text)                          answer)   answer)
```

Three apps in one repo:

| App | Folder | What it is |
|---|---|---|
| Backend | `apps/backend` | Python FastAPI server on `localhost:8000`: STT, TTS, RAG, chat, sessions |
| Frontend | `apps/frontend` | React + Vite web app (lobby, tutor page, library/setup page) |
| Desktop | `apps/desktop` | `launch.mjs` opens the frontend in a borderless Chrome/Edge `--app` window (no Electron, to save RAM) |

The LLM and the embedding model run in **Ollama**, a separate local server on `localhost:11434`.

---

## 2. Hardware and hard constraints

**Dev laptop (every number in this guide):** Intel Core i7-6600U, 6th Gen, **2 physical cores / 4
threads**, 15 W, **8 GB RAM**, Windows 10 Pro 19045, CPU only, no GPU.

**Target laptops (not measured yet):**
- HP ZBook 15 G5/G6: i5/i7 8th/9th Gen, 16 GB RAM, 256 GB storage.
- HP EliteBook 840 G3–G7: i5/i7 6th–10th Gen, 16 GB RAM, 256 GB storage.

Both have more RAM and most have newer CPUs, so they should do at least as well. This has **not**
been measured.

**Hard constraints**
- **Offline at question time.** No cloud API, no internet. Setup downloads are one-time.
- **One device.** A LAN server was ruled out. The laptop runs everything: Ollama, backend, browser.
- **CPU only.** Writing speed (decode) is about **5 tokens/s** and is a CPU limit, not a RAM limit.
  Memory tuning was tried and changed nothing.
- **Priority order (from the user):** 1) latency, 2) accuracy/groundedness, 3) speech smoothness.
  Target first audio 3–4 s (ideal), **7–8 s accepted**.

**RAM budget (resident while tutoring; file sizes on disk):**

| Item | Size | Stays loaded? |
|---|---|---|
| gemma2:2b (LLM) | 1.6 GB | Yes (`OLLAMA_KEEP_ALIVE=-1`) |
| bge-m3 (embeddings) | 1.2 GB | Yes (measured: unloading it cost more in reloads than it saved) |
| IndicConformer (Hindi/Marathi STT, fp32) | 471 MB | Loaded on first use |
| Whisper base.en int8 (English STT) | 154 MB folder | Loaded on first use |
| Piper voice (one language at a time) | ~60–75 MB each (212 MB for all three + espeak data) | One voice resident |
| Textbook database `library.db` | 33 MB (3,573 chunks) | On disk, SQLite |
| Chrome app window + OS | the rest | — |

---

## 3. Architecture

### 3.1 Components

```
┌──────────────────────── Borderless Chrome/Edge window (apps/desktop/launch.mjs) ────────────────────────┐
│  React frontend (apps/frontend)                                                                          │
│                                                                                                          │
│   StartPage (lobby)          TutorPage (chat)                         SetupPage (library)                │
│   - language/class/subject   - mic → useIndicSpeechToText             - upload PDFs (+ class,           │
│     built from the library   - useTutorSession (orchestrator)           subject, medium)                 │
│   - readiness: STT/TTS/model - streams answer, splits into clips      - shows job progress               │
│   - primes a session         - useBackendTts plays clips gap-free                                        │
└───────────┬─────────────────────────────┬──────────────────────────────────────┬────────────────────────┘
            │ HTTP (localhost:8000)       │                                      │
            ▼                             ▼                                      ▼
┌──────────────────────────────── FastAPI backend (apps/backend) ─────────────────────────────────────────┐
│  /api/stt ──► services/stt.py ──► sherpa-onnx ──► IndicConformer (hi/mr) | Whisper base.en (en)        │
│  /api/tts ──► services/tts.py ──► sherpa-onnx ──► Piper voice (hi/mr/en)                                │
│  /api/chat/stream ──► routers/chat.py                                                                    │
│        ├─ sessions.py        (history in memory, passages already shown, last passage)                   │
│        ├─ rag/retrieval.py   (embed question → vector + keyword search → gate → fuse → top k)            │
│        │     └─ rag/store.py  ──► data/library.db (SQLite: chunks, FTS5 trigram index, sqlite-vec vec0)  │
│        ├─ tutor.py           (persona + rules + the student's turn)                                      │
│        └─ ollama_client.py   (chat stream, background re-prime)                                          │
│  /api/library/* ──► rag/ingest.py ──► pdf_text.py (PyMuPDF + legacy_hindi) → chunking → bge-m3 → store  │
└───────────────────────────────────────────────┬──────────────────────────────────────────────────────────┘
                                                │ HTTP (localhost:11434)
                                                ▼
                         ┌────────────── Ollama 0.34.0 (llama.cpp) ──────────────┐
                         │  gemma2:2b  — writes answers  (/api/chat)              │
                         │  bge-m3     — turns text into vectors (/api/embed)     │
                         │  KV cache of the last prompt (reused if prefix matches)│
                         └────────────────────────────────────────────────────────┘
```

### 3.2 One question, end to end

```
 Student            Frontend                      Backend                         Ollama
   │  speaks          │                              │                               │
   │─────────────────►│ record 16 kHz, detect speech │                               │
   │                  │── POST /api/stt (partial) ──►│ IndicConformer (every ~1.1 s)  │
   │  stops (1.1 s    │── POST /api/stt (final) ────►│ transcript                     │
   │  of silence)     │◄──────── "काली मृदा ..." ────│                               │
   │                  │── POST /api/chat/stream ────►│ follow-up? no                  │
   │                  │                              │── /api/embed (question) ──────►│ bge-m3
   │                  │                              │   vector + keyword search,     │
   │                  │                              │   gate, fuse, pick 1 passage   │
   │                  │◄──── SSE "sources" (page) ───│                               │
   │                  │                              │── /api/chat (stream) ─────────►│ gemma2:2b
   │                  │                              │   prefill (new part only)      │ (cache)
   │                  │◄──── SSE tokens ─────────────│◄────────── tokens ─────────────│ decode
   │                  │ first 18–28 chars ready      │                               │
   │                  │── POST /api/tts (clip 1) ───►│ Piper → WAV                    │
   │◄── first audio ──│ play clip 1; keep writing,   │                               │
   │                  │ synthesising, playing        │                               │
   │                  │◄──── SSE done + metrics ─────│── re-prime (background) ──────►│ reads the answer
   │◄── last audio ───│                              │   so the next turn is cached   │ into the cache
```

### 3.3 What changed vs. the last commit (`f9f16ad`)

| | At `f9f16ad` | Now |
|---|---|---|
| Where textbook passages go | Top of the **system prompt** | End of the **student's turn** |
| Passages per question | 3 whole chunks in code (`rag_top_k=3`) | **1**, cut to its first ~110 tokens (`RAG_TOP_K=1`) |
| Cache reuse | Broken: the top changed every question, so everything was re-read | Persona and history cached; only the new turn is read |
| Reply rules | Resent every turn (47–56 tokens) | In the cached persona; 7–10 token reminder per turn |
| Follow-ups | Searched on their own words (often wrong) | Reuse the previous passage, no search |
| After each answer | Nothing | Background re-prime, so the next turn doesn't re-read the answer |
| Hindi PDF text | pypdf: 100% of Hindi corrupted | PyMuPDF plus legacy-font converter |
| Search scope | Class only | Class + subject + medium |
| First word, new textbook question | 47–54 s (measured, 18-book library) | 4.3–7.1 s (measured live) |

---

## 4. Models and libraries — what and why

| Job | Choice | Version / size | Why this one | Rejected alternatives |
|---|---|---|---|---|
| Write answers | **gemma2:2b** in Ollama | 1.6 GB | Smallest model that writes coherent Hindi and Marathi | qwen2.5:1.5b (broken Hindi/Marathi), gemma3:1b (2× faster, wrong/incoherent Hindi), Navarasa Indic fine-tune (didn't work here) |
| Model server | **Ollama** | 0.34.0 | Local, simple HTTP API, keeps the model loaded, prefix cache | — |
| Embeddings (search) | **bge-m3** | 1.2 GB, 1024 dims | Only tested model that ranks Hindi→English and Marathi→English correctly | nomic-embed-text (scored an off-topic passage *higher* than the right one for Hindi), paraphrase-multilingual |
| Hindi/Marathi STT | **AI4Bharat IndicConformer-600M** (CTC) on sherpa-onnx | fp32, 471 MB | Built for Indian languages; outputs correct Devanagari; no language auto-detect, so no Hindi/Urdu mix-up | int8 export (~2× word errors: Hindi ~16% → ~30%), Chrome Web Speech (not offline for Hindi on Windows 10) |
| English STT | **Whisper base.en** (int8) on sherpa-onnx | 154 MB | Handles Indian-accented English, fully offline | Browser Web Speech (Chrome sends audio to Google) |
| TTS | **Piper VITS voices** on sherpa-onnx | hi_IN-priyamvada-medium, mr_IN-google-medium, en_US-amy-low | Fast on CPU, female Hindi voice, same sherpa-onnx package as STT | Browser MMS-TTS (~15 s per sentence), Indic Parler-TTS (0.9B, too slow), IndicVoice-82M (Hindi/Bengali only), browser speechSynthesis (removed) |
| PDF text | **PyMuPDF** | 1.28.2 | Follows the fonts' Unicode maps; reports each span's font (needed for legacy Hindi) | pypdf (corrupted 100% of NCERT Hindi) |
| Vector search | **sqlite-vec** `vec0` | 0.1.9 | One SQLite file; class as partition key, subject and medium as filters | — |
| Keyword search | SQLite **FTS5**, trigram tokenizer | built in | Trigrams match Hindi word forms (कोशिका / कोशिकाओं) | — |
| Backend | FastAPI + uvicorn, httpx, pydantic-settings | 0.115.6 / 0.32.1 | Async streaming (SSE), settings from `.env` | — |
| Speech runtime | **sherpa-onnx** | 1.13.6 | Prebuilt wheel, no compiler; runs both STT and TTS | — |

---

## 5. Speech-to-text (STT)

### 5.1 Which engine, and why

| Language | Engine | Model file | Why |
|---|---|---|---|
| Hindi | IndicConformer-600M, CTC | `models/indicconformer/model.onnx` (fp32) | Trained on Indian languages; outputs native script directly |
| Marathi | Same model | same file | One multilingual model covers both; no second download |
| English | Whisper base.en, int8 | `models/stt/sherpa-onnx-whisper-base.en/` | Good on Indian-accented English; small |

All three run on the **backend** through sherpa-onnx. The frontend sends audio for every language
(`useTutorSpeechToText.ts` always routes to `/api/stt`).

**Why not the browser's speech recognition?**
- Chrome's built-in recogniser sends audio to Google, so it isn't offline.
- Chrome's on-device Hindi recognition did not work on this Windows 10 laptop (tested).
- The backend engines behave the same on every machine.

**Why fp32 and not int8 for IndicConformer?** int8 roughly doubles the word error rate in Hindi
(~16% → ~30%). Saving 280 MB is not worth transcripts that are twice as wrong.

**Why not Whisper for Hindi too?** Whisper auto-detects language and can write Hindi speech in Urdu
script or English letters. IndicConformer is told the language and outputs Devanagari.

### 5.2 How a recording becomes text

Frontend (`hooks/stt/useIndicSpeechToText.ts`):

| Step | Constant | Value |
|---|---|---|
| Record the mic at 16 kHz mono | `TARGET_RATE` | 16000 |
| Treat audio as speech above this loudness (RMS) | `SPEECH_RMS` | 0.012 |
| Send "audio so far" for a live grey transcript every… | `PARTIAL_INTERVAL_MS` | 1100 ms |
| …only if at least this much new audio arrived | `PARTIAL_MIN_NEW_SEC` | 0.4 s |
| Longest audio sent for a partial | `PARTIAL_MAX_SEC` | 15 s |
| End of question = this much silence (or tap Send) | `SILENCE_HANGOVER_MS` | 1100 ms |
| Longest audio sent for the final transcript | `FINAL_MAX_SEC` | 30 s |

Backend (`services/stt.py`):
1. `POST /api/stt` receives a 16-bit mono WAV and the language.
2. It picks the engine (`hindi`/`marathi` → IndicConformer, `english` → Whisper) and loads it on
   first use (`lru_cache`, up to 2 engines).
3. It decodes with `STT_NUM_THREADS=4`. A lock lets only one decode run at a time.
4. It returns `{ "text": "..." }`.

At startup the backend warms `WARM_LANGUAGE` (English) with a 0.4 s silent decode. The lobby's
readiness check loads and warms the selected language.

**Why the live transcript isn't truly live.** IndicConformer is a *batch* model: it needs the whole
clip. The grey text is the same model re-run on the audio so far, every 1.1 s. The clean
transcript arrives after the 1.1 s silence plus one decode.

**STT cost.** Normally a decode takes about a second after the pause (not re-timed this week). It
is very sensitive to CPU load: with a background job running, one decode took **175 s**
(2026-09-11). Keep the laptop otherwise idle.

---

## 6. The textbook library — upload and ingestion

### 6.1 What happens when you upload a PDF

```
 PDF + class + subject + medium (Setup page)
   │  POST /api/library/documents  → returns a job id at once (never blocks)
   ▼
 1. SHA-256 of the file ─── already in the library? → stop ("already there")
 2. Extract text per page with PyMuPDF (pdf_text.py)
      └─ Page uses a legacy 8-bit Hindi font (Walkman-Chanakya, Kruti Dev, DevLys)?
           → convert those spans to Unicode Devanagari (legacy_hindi.py)
 3. Clean: collapse doubled vowel signs (न्यााय → न्याय), drop repeated page furniture
 4. Checks:
      no text layer at all                → ERROR "scanned PDF, run OCR first"
      broken Devanagari / very little Hindi → store it anyway WITH A WARNING
 5. Chunk: pack paragraphs to ~1,200 chars (max 2,000, min 40), 180-char sentence overlap,
           no overlap across a heading, duplicates dropped
 6. Embed each chunk with bge-m3, 16 per call, with a breadcrumb in front:
      "Class 6 > Geography > <heading>\n\n<chunk text>"   (breadcrumb is not shown to the LLM)
 7. Store: documents, chunks, FTS5 trigram index, vec0 vector table
 8. Clear the pinned-corpus cache so the new book is visible immediately
```

- **One upload at a time** (a lock), because it competes with the tutor for the same 2 cores.
- **Leaving the page doesn't stop a job**: it runs on the backend. Keep the page open until the
  last file has been *sent*.
- **If embedding fails partway, the whole document is rolled back.** A half-embedded book would
  look like the tutor not knowing the later chapters.

### 6.2 Why `legacy_hindi.py` exists

NCERT typesets Hindi Social Science books in **Walkman-Chanakya905**, an old 8-bit font that draws
Devanagari shapes using Latin character codes. Any PDF library, PyMuPDF included, returns
`lkekftd foKku` instead of `सामाजिक विज्ञान`. No package we could use fixed this: the available
converters are GPL-3.0, which would impose GPL obligations on this project. So we wrote our own:
- A table of about 128 glyphs, matched longest first.
- Moving the short i-vowel sign (ि) after its consonant cluster, and the reph (र्) before its syllable.
- Handling Chanakya's hook glyphs for क and फ.

Only spans whose font is legacy are converted; English and Unicode text are untouched. The
Geography book went from **0% to 98.4% Devanagari** (0.06 broken clusters per 100 characters). 45
real phrases from the book are pinned in `tests/test_legacy_hindi.py`.

### 6.3 The database (`apps/backend/data/library.db`)

| Table | Holds | Used for |
|---|---|---|
| `documents` | title, filename, class, subject, medium, SHA-256, pages | Library list, duplicate check |
| `chunks` | chunk text, heading, page range, document | What the LLM reads, citations |
| `chunks_fts` (FTS5, trigram) | keyword index over chunk text | Keyword search leg |
| `vec0` table | 1024-dim vector per chunk; **class = partition key**; subject and medium = filters | Meaning search leg |

**Library right now:**

| Books | Class · Subject · Medium | Chunks |
|---|---|---|
| System Analysis & Design | 6 · Computer Science · English | 2,139 |
| NCERT Class 10 Geography (legacy font, converted) | 6 · Geography · Hindi | 836 |
| 5 Hindi Veena files | 6 · History · Hindi (label kept as-is by decision) | 174 |
| 13 Science files | 5 · Science · English | 424 |
| **Total** | | **3,573** |

**Upload speed (measured 2026-09-11):** the 112-page Geography book took 603 s (~5.4 s/page); the
18–26-page Science chapters took 57–98 s each (~3–4 s/page). All 19 files together took 15.9 min.

---

## 7. Retrieval — how a question finds its passage

Code: `routers/chat.py::_retrieve_context` → `rag/retrieval.py::retrieve`.

### 7.1 Three paths, checked in this order

```
 question
   │
   ├─ 1. PINNED CORPUS?  The selected books fit in 1,500 tokens?
   │       yes → the whole book sits in the system prompt, no search at all
   │       (none of today's books are this small, so this path is not used)
   │
   ├─ 2. FOLLOW-UP?  ≤ 8 words AND contains a back-reference word
   │       (इसका, यह, उदाहरण, this, it, example, again, हे, त्याचे …)
   │       yes → reuse the previous answer's passage; no embedding, no search,
   │             nothing pasted (it's already in the conversation)
   │
   └─ 3. NORMAL SEARCH (every new question) ▼
```

### 7.2 Normal search, step by step

| # | Step | Setting | What it does |
|---|---|---|---|
| 1 | Embed the question with bge-m3 | — | One `/api/embed` call. Measured 0.09–1.1 s depending on load |
| 2 | **Dense (meaning) search** | `RAG_CANDIDATES=50` | 50 nearest chunks, **only** in the lobby's class + subject + medium |
| 3 | **Ceiling gate** | `RAG_CEILING_HI=0.50`, `EN=0.51`, `MR=0.59`, romanized `0.0` | If even the best chunk is farther than the ceiling, the library doesn't cover it: answer without the book, cite nothing |
| 4 | **Relative gate** | `RAG_RELATIVE_MARGIN=0.12` | Keep only chunks within 0.12 of the best one |
| 5 | **Lexical (keyword) search** | 50 candidates, FTS5 BM25 | Only chunks that passed the gate, or sit right next to one, may join |
| 6 | **Fuse** both lists | `RAG_RRF_K=60` | Reciprocal Rank Fusion: a chunk found by both searches rises |
| 7 | **Exercises yield** | slack 0.03 (code) | An exercise chunk ("(क) … लिखिए") gives way to an explanation within 0.03 distance |
| 8 | Take the top **k** | `RAG_TOP_K=1` | One passage |
| 9 | **Trim** to its first sentences | `RAG_PASSAGE_TOKEN_CAP=110` | Keeps the head in order (textbook paragraphs lead with the definition) |
| 10 | **Budget** | `RAG_CONTEXT_TOKEN_BUDGET=4000` | Whole passages only; k drops before a passage is cut (never binds at k=1) |
| 11 | **Skip passages already shown** | `RAG_DEDUP_CONTEXT=true` | A passage pasted earlier this session isn't pasted again |

Distances are cosine distances from bge-m3: **smaller = more relevant**. The scale shifts with
language (a correct English hit sits around 0.21–0.44, a correct Hindi hit around 0.27–0.47), which
is why each language has its own ceiling.

**Why the gate runs before fusion.** After fusion only ranks are left, and the distances needed to
say "the book doesn't cover this" are gone. Keyword search can't tell coverage from coincidence, so
it only decides order, never whether there is an answer.

**What the LLM receives (the passage block):**

```
Textbook excerpts:

[1] Class-X-NCERT-Books-Geography - <heading> - p. 29
<first ~110 tokens of the chunk>
```

### 7.3 Example search results (2026-09-11, live library)

| Question | Top passage | Right book? | Passage type |
|---|---|---|---|
| किस राज्य में काली मृदा मुख्य रूप से पाई जाती है | Geography p.29 | Yes | **Exercise question** ("(v) इनमें से किस राज्य में…") |
| बहुउद्देशीय नदी परियोजनाएं | Geography p.50 | Yes | **Exercise question** |
| भारत में वनस्पति जात और प्राणी जात | Geography p.23 | Yes | Explanation |
| राजा बना लड़का फरियाद कैसे सुनता था? | Veena ehve102 p.1 | Yes | Story text (answer) |
| What causes scurvy? | Science fecu103 p.9 | Yes | Explanation ("caused due to deficiency of Vitamin C") |
| What is a laboratory thermometer? | Science fecu107 p.9 | Yes | **Activity/exercise** |

All six find the right book and page. In three, the top chunk is an exercise that repeats the
student's words, and no explanation was within 0.03 of it. **This is the main open accuracy issue.**

---

## 8. The LLM — prompt layout, prefill, decode

### 8.1 Two stages

```
            gemma2:2b
               │
     ┌─────────┴──────────┐
  PREFILL               DECODE
  read the prompt       write the answer
  cost: NEW tokens      cost: every output token
  ~38–50 ms each        ~200 ms each (~5 tok/s)
  cached: ~2 ms each    not helped by the cache
```

The first word appears after retrieval, prefill, and one decode step. The voice starts after the
first clip (18–28 characters) has been written.

### 8.2 What the prompt looks like

The prompt is a list of messages. **Only the end changes from turn to turn**, which is what makes
the cache work.

```
┌─ system ───────────────────────────────────────────────────────────── cached ─┐
│ Persona: "You are a patient tutor for a school student…"                       │
│ Today's focus is Geography… Pitch it so a Class 6 student can follow…          │
│ RETRIEVAL_RULE: "You may be given excerpts from the student's own textbook…"   │
│ Keep answers under 85 words (Devanagari) / 110 (English). Plain prose, no lists│
│ Reply in Hindi. Most important rule: Answer in 4-5 sentences: what, how/why,   │
│ one everyday example, the one thing to remember…                               │
│ Write in Hindi using the Devanagari script… ('AI' as 'ए॰आई॰')…                  │
│ Rules for every reply: Plain sentences, one paragraph, no bullets or bold.     │
│ Under 85 words. Do not end with a question. Reply only in Hindi (Devanagari).  │
│ When the student's message begins with textbook text, answer using the facts   │
│ in that text, in your own simple words, and never mention the text itself.     │
├─ user / assistant … (earlier turns, up to 20 messages) ───────────── cached ──┤
├─ user (this turn) ──────────────────────────────────────────── NEW, read now ─┤
│ Textbook excerpts:                                                              │
│ [1] Class-X-NCERT-Books-Geography - … - p. 29                                   │
│ <≤110 tokens of passage>                                                        │
│                                                                                 │
│ किस राज्य में काली मृदा मुख्य रूप से पाई जाती है?                                   │
│                                                                                 │
│ Reply only in Hindi (Devanagari).          ← 10-token reminder (English: "Under 110 words.")
└─────────────────────────────────────────────────────────────────────────────────┘
```

Why this layout:
- **Passages go in the turn, not the system prompt.** Changing the system prompt changes the start
  of the prompt, and the whole thing is re-read. Measured: 27.7 ms/token when excerpts grew in the
  system prompt vs 5.3 ms/token when attached to the turn.
- **Rules live in the persona, with a short reminder at the end.** gemma2:2b follows the *end* of
  the prompt most. With no reminder, answers ran 118–159 words. With the full rules on every turn,
  each question paid 47–56 extra new tokens (~1.5–1.7 s).
- **The stored user turn is exactly what was sent** (passage included), so the history replays
  byte-for-byte and stays cached.

### 8.3 Generation settings

| Setting | Value in effect | Why |
|---|---|---|
| `TEMPERATURE` | 0.7 English | Natural phrasing |
| `TEMPERATURE_NON_ENGLISH` | 0.6 | Less script drift; below ~0.5 the model loops phrases in Hindi |
| `REPEAT_PENALTY` / `REPEAT_LAST_N` | 1.15 / 128 | Stops loops; above ~1.2, Hindi becomes word salad |
| `MAX_TOKENS` / `MAX_TOKENS_NON_ENGLISH` | 220 / 300 (`.env`) | A safety net that should never bind; answer length comes from the word budget (85 / 110 words) |
| `NUM_CTX` | 4096 (`.env`) | Context window: persona + 10 turns at k=1 fits (~2,900 tokens, estimate) |
| `OLLAMA_NUM_THREAD` | 4 (`.env`) | Measured fastest for prefill: 4 threads 34.8, 3 threads 39.7, 2 threads 43.2 ms/token |
| `OLLAMA_KEEP_ALIVE` | -1 | Never unload; a cold reload is 10–20 s |
| `MAX_HISTORY_MESSAGES` | 20 (`.env`) | 10 question-answer pairs replayed; sized so a lesson doesn't slide |
| Style | `teach` | 4–5 sentences: what → how/why → everyday example → the thing to remember |

---

## 9. The cache — why turns are fast

### 9.1 How Ollama's cache works

After each request, Ollama keeps the model's working memory (the KV cache) for every token of that
prompt. When the next prompt **starts with exactly the same tokens**, it skips them and reads only
from the first difference onward.

Measured cost model (2026-09-10):

```
prefill time ≈ (NEW tokens × ~38–50 ms) + (TOTAL tokens × ~2 ms)
```

What a turn **adds** matters far more than how long the prompt is. That's the whole design.

### 9.2 The Ollama 0.34 catch, and the re-prime fix

gemma2 uses *sliding-window attention*. With it, Ollama 0.34 (llama.cpp server) can resume only
from a **checkpoint**, and it saves one only at the **end of each prompt**, before the reply. So the
tokens it *generated* were never reusable, and every next turn re-read the previous answer (65–130
tokens, 2.5–5 s).

**Fix: re-prime (`OLLAMA_REPRIME_AFTER_REPLY=true`).**
1. As soon as an answer finishes, the backend sends Ollama the conversation **up to and including
   that answer**, asking for 1 token (`num_predict=1`; `0` means "unlimited" in Ollama).
2. That creates a checkpoint exactly where the next question will start.
3. It runs **while the answer is being spoken** (~3.5 s of work inside a 15–25 s answer).

If the student asks before it finishes, their request waits behind work it needed anyway, so it is
never slower than without it.

Measured: next-turn prefill **5.3–6.0 s → 2.46 s** (median, controlled test). Follow-up first word
live: **7.0–7.4 s → 2.4–3.0 s**.

### 9.3 Things that break the cache

| Breaks the cache | Why | What we do |
|---|---|---|
| Changing anything near the top (persona, passage in the system prompt) | Everything after the change is re-read | Passages in the turn; persona fixed per session |
| Sending different `num_ctx` / `num_thread` than the warm-up | Ollama reloads the model | `_load_options()` shared by warm-up, chat and prime |
| History sliding (message 21 drops message 1) | The start of the prompt changes | `MAX_HISTORY_MESSAGES=20`; the re-prime also absorbs the slide |
| Another request in between (a second tab, an upload's embedding) | Ollama caches only the last prompt | One session at a time; upload outside lessons |
| Changing language/class/subject | New persona | Lobby re-primes for the new combination |

---

## 10. Worked example — a lesson, call by call

Class 6 · Geography · Hindi. Token counts are **estimates** from the prompt pieces; times are the
**measured** ranges from the live timing panel.

### Lobby (before the first question)

| Call | What | Cost |
|---|---|---|
| `GET /api/stt` (readiness, Hindi) | Load and warm IndicConformer | One-time |
| `GET /api/tts` (readiness, Hindi) | Load and warm the Hindi voice | One-time |
| `POST /api/chat` with `max_tokens=1`, message "warm up" | **No retrieval.** Ollama reads the persona (~500 tokens) and caches it | ~15–20 s (estimate: ~500 tokens × ~35 ms), while the student is still in the lobby |

The chat page then continues **that same session**, so question 1 starts from a warm cache.

### Question 1: "किस राज्य में काली मृदा मुख्य रूप से पाई जाती है?"

| # | Call | Detail |
|---|---|---|
| 1 | `POST /api/stt` × n | Partials every 1.1 s, then the final transcript |
| 2 | `POST /api/chat/stream` | — |
| 3 | → Ollama `/api/embed` (bge-m3) | Question vector |
| 4 | → SQLite vector + FTS5 search | Geography p.29 chosen, trimmed to ≤110 tokens |
| 5 | → Ollama `/api/chat` (stream) | Prompt ≈ persona 500 (cached) + passage and question ~150 (**new**) |
| 6 | → `POST /api/tts` per clip | Clip 1 = first 18–28 characters |
| 7 | → Ollama `/api/chat` `num_predict=1` (**re-prime**) | Reads the ~100-token answer into the cache while it's spoken |

First word **4.3–7.1 s** (measured). First audio about 2 s later (estimate).

### Question 2 (follow-up): "इसका एक उदाहरण दीजिए"

| # | Call | Detail |
|---|---|---|
| 1 | `POST /api/stt` | Transcript |
| 2 | `POST /api/chat/stream` | 5 words + "इसका" → **follow-up**: no embed, no search |
| 3 | → Ollama `/api/chat` (stream) | Everything up to answer 1 is cached (thanks to the re-prime); new ≈ 10–20 tokens |
| 4 | → re-prime | In the background |

First word **2.4–3.0 s** (measured). Citation: still Geography p.29.

### Question 3 (new topic): "बहुउद्देशीय नदी परियोजनाएं क्या हैं?"

Same as question 1: embed, search (Geography p.50), ~150 new tokens, re-prime. The p.29 passage
stays in the history above and costs nothing extra.

### How the prompt grows

```
after lobby : [persona ~500]                                                  cached
Q1          : [persona][warm-up][P1 + Q1 ~150 NEW]                → A1 ~100
Q2 follow-up: [persona][warm-up][P1+Q1][A1 cached by re-prime][Q2 ~15 NEW] → A2
Q3 new topic: [persona][warm-up][P1+Q1][A1][Q2][A2][P3 + Q3 ~150 NEW]      → A3
…
Q10         : ~2,900 tokens in total, but still only ~150 NEW              (estimate)
Q11         : history is full (20 messages): the oldest pair drops → the start
              changes → that turn re-reads more (the re-prime after Q10 absorbs most of it)
```

**Context length grows every turn. What stays small is the new part.**

### Every call to Ollama per turn

| Turn type | `/api/embed` | `/api/chat` (answer) | `/api/chat` (re-prime) |
|---|---|---|---|
| Lobby warm-up | 0 | 1 (1 token) | 0 |
| New textbook question | 1 | 1 | 1 (background) |
| Follow-up | 0 | 1 | 1 (background) |
| Off-syllabus (gate says no) | 1 | 1 | 1 — answered without the book, no citation |

---

## 11. Text-to-speech (TTS)

### 11.1 Voices

| Language | Piper voice | Notes |
|---|---|---|
| Hindi | `hi_IN-priyamvada-medium` | Female |
| Marathi | `mr_IN-google-medium` | 9-speaker model, speaker 0 |
| English | `en_US-amy-low` | "low" export: smaller and faster |

- Voice files live in `apps/backend/models/tts/<language>/` (`model.onnx`, `tokens.txt`,
  `warmup.txt`) plus one shared `espeak-ng-data/`.
- `scripts/package_tts_voices.py` downloads them from the official `rhasspy/piper-voices` repo.
- Piper has Indic voices for hi, mr, te, ml, bn, ne and ur. **No Piper voice exists for Tamil,
  Kannada, Gujarati, Punjabi, Odia or Assamese.**

### 11.2 How the answer is spoken

Frontend (`useTutorSession.ts` + `useBackendTts.ts`):
1. Tokens stream in. `drainSentences` cuts the text into **clips** at a sentence end (। . ! ?), a
   comma, or a word boundary.
2. Each clip goes to `POST /api/tts` and comes back as a WAV. Clips play **back-to-back** through Web Audio.
3. **Clip sizes ramp up** so the voice never waits for a long sentence:

| Clip | Min–max characters |
|---|---|
| 1 | 18–28 |
| 2 | 20–40 |
| 3 | 24–52 |
| 4 onward | 30–64 |

4. A failed clip request is retried once after 300 ms. The error banner clears on the next success.

Backend (`services/tts.py`):
- One voice resident (`lru_cache(maxsize=1)`), keyed on the **lowercased** language. "Hindi" and
  "hindi" used to be two keys, and the swap cost 11.5 s.
- `warm()` speaks the real sentence from `warmup.txt` once per load. The first synthesis is what
  allocates ONNX memory and loads espeak's phoneme rules.
- `TTS_NUM_THREADS=2` (leaves cores for the LLM, which is still writing). `TTS_SPEED=0.9` (`.env`).

**Why clips ramp (measured rates):** gemma2 writes Hindi at ~12.7 characters/s; Piper *speaks* ~13
characters/s; synthesis costs ≈ 0.02 s + 0.0198 s/character under load. Writing ≈ speaking, so a
gap opens only when the next clip is much longer than the one playing. Simulated on three real
Hindi answers: silence after the first clip **12.2 / 5.0 / 7.6 s → 1.5 / 1.9 / 1.7 s**; gap between
clips 1 and 2 **9.6 / 1.4 / 2.8 s → 0.4 / 0.5 / 0.5 s**. Simulated, not yet measured in the browser.

---

## 12. Latency — where every second goes

### 12.1 A new textbook question (Hindi)

```
student stops speaking
 ├─ silence detection        1.1 s   (SILENCE_HANGOVER_MS)
 ├─ STT final decode         ~1 s    (idle CPU; much more under load)
 ├─ retrieval (embed+search) ~0.1–1 s
 ├─ prefill (~150 new tokens) ~4–6 s
 ├─ first clip written       ~1.5–2 s   (18–28 chars at ~12.7 chars/s)
 └─ first clip synthesised   ~0.5 s
                                        ─────────────
 first audio after the request is sent:  ~6–9 s  (estimate; first word measured 4.3–7.1 s)
 follow-up:                              ~4–5 s  (first word measured 2.4–3.0 s)
```

The in-app **Timing & retrieval** panel shows the backend part of this for every answer: retrieval,
TTFT (time to first token), prefill, decode, prompt tokens, tokens/s and groundedness.

### 12.2 What each lever is worth (measured)

| Lever | Saves |
|---|---|
| Passages moved from system prompt to the turn | 47–54 s → 9.4 s first word |
| Re-prime after each answer | 2.5–5 s on the next turn |
| Follow-up reuse | ~0.3 s search + 70–110 new tokens (~3–5 s) |
| Rules into the persona | 46 new tokens, ~1.5–1.7 s |
| Passage cap 110 tokens (vs whole chunks of 341–375) | ~10 s on long chunks |
| k=1 vs k=2 | 2.9–4.9 s |
| 4 threads vs 2 | ~20% of prefill |
| Ollama priority AboveNormal (start.ps1) | the same prompt: ~7.3 s idle vs ~20 s with the app window competing |
| Lobby warm-up | the persona is never read during a question |

### 12.3 What we can't speed up on this laptop

- **Decode, about 5 tokens/s.** A CPU limit. Hidden by speaking while writing, not reduced.
- **Other CPU load.** Google Meet, an upload, or a benchmark can take a normal 6 s turn to 43–56 s
  (measured 2026-09-11).
- **Heat.** Identical work varies up to 2.4×.

---

## 13. Accuracy — groundedness and citations

**Groundedness** (`rag/metrics.py`) is the share of the answer's content-word **character trigrams**
that also appear in the passages it was given. It is 0 to 1; answers with fewer than 8 trigrams are
not scored. Trigrams, because Hindi inflects: कोशिका and कोशिकाओं share the stem.

| | Value |
|---|---|
| Target | 0.40–0.45 |
| Before the instruction change | 0.179 median (14-question A/B) |
| Now ("Answer using the facts in the text above, in your own simple words") | **0.266** median; key fact present 10/14 |
| Status | **Not met** |

**Citation honesty**
- The Hindi ceiling was re-measured on clean text: 0.58 → **0.50**. Off-syllabus questions shown
  as "From your textbook": **4/10 → 0/10**. Answerable questions kept: 11/12 (a bare title at 0.532
  missed).
- When groundedness is under 0.05, the bubble says **"Not drawn from your textbook · closest page N"**
  instead of claiming the book.
- Romanized Hindi ("gharshan bal kya hai") has **retrieval switched off** (ceiling 0.0). bge-m3
  ranks the wrong passages closer than the right ones for Latin-script Hindi. The tutor answers
  without the book instead of citing a wrong page.

**Why groundedness is still low**
1. **Exercise chunks win the search** (3 of 6 test questions, §7.3). The model gets a question, not
   the explanation.
2. **One short passage.** Up to ~110 tokens; facts later in the chunk are cut.
3. gemma2:2b paraphrases and adds its own example (which the `teach` style asks for).

---

## 14. Every parameter

Backend settings live in `apps/backend/app/config.py`; `apps/backend/.env` overrides them. **Names
must match the field names exactly.** pydantic ignores unknown names silently, which is how
`OLLAMA_NUM_THREAD` and `MAX_TOKENS_NON_ENGLISH` once did nothing for weeks.

### 14.1 LLM and Ollama

| Parameter | In effect | Code default | What it does | Raise it → | Lower it → |
|---|---|---|---|---|---|
| `OLLAMA_MODEL` | gemma2:2b | same | The answer model | — | — |
| `OLLAMA_HOST` | 127.0.0.1:11434 | localhost:11434 | Where Ollama runs | — | — |
| `OLLAMA_KEEP_ALIVE` | -1 | -1 | Keep the model loaded forever | — | Cold 10–20 s reloads |
| `WARM_MODEL_ON_STARTUP` | true | true | Load the LLM when the backend starts | — | First question pays the load |
| `OLLAMA_NUM_THREAD` | **4** | 0 (auto) | CPU threads | >4 oversubscribes this CPU | Slower prefill (2 = +24%) |
| `NUM_CTX` | **4096** | 6144 | Context window (tokens) | More RAM | Overflow drops the system prompt silently |
| `MAX_HISTORY_MESSAGES` | **20** | 10 | Past messages replayed (20 = 10 turns) | Longer memory, bigger prompt | Earlier slides and cache loss |
| `SESSION_TTL_MINUTES` | 180 | 180 | Idle session expiry | — | — |
| `TEMPERATURE` / `_NON_ENGLISH` | 0.7 / 0.6 | same | Randomness | Drift, less accurate | <0.5 loops in Hindi |
| `REPEAT_PENALTY` / `REPEAT_LAST_N` | 1.15 / 128 | same | Anti-repetition | >1.2 garbles Hindi | Phrase loops |
| `MAX_TOKENS` / `_NON_ENGLISH` | **220 / 300** | 200 / 240 | Hard cap on answer tokens | — | Cuts answers mid-sentence |
| `OLLAMA_REPRIME_AFTER_REPLY` | true | true | Background re-prime | — | Follow-ups +2.5–5 s |
| `OLLAMA_TIMEOUT_SECONDS` | 180 | 180 | Read timeout | — | — |
| `TUTOR_RULES_IN_PERSONA` | true | true | Rules cached in the persona | — | false = rules every turn (+1.5 s) |

### 14.2 Retrieval (RAG)

| Parameter | In effect | Code default | What it does |
|---|---|---|---|
| `RAG_ENABLED` | true | true | Use the textbook at all |
| `RAG_EMBEDDING_MODEL` / `_DIMS` | bge-m3 / 1024 | same | Must match what the library was built with |
| `RAG_EMBED_QUERY_KEEP_ALIVE` | -1 | -1 | Keep bge-m3 loaded (unloading measured worse) |
| **`RAG_TOP_K`** | **1** | 3 | Passages per question. Each extra ≈ +4–5.5 s (estimate); measured k=2 +2.9–4.9 s |
| `RAG_CANDIDATES` | 50 | 50 | Candidates per search leg |
| `RAG_RRF_K` | 60 | 60 | Fusion damping |
| `RAG_RELATIVE_MARGIN` | 0.12 | 0.12 | Keep hits within this of the best |
| `RAG_CEILING_EN` / `_HI` / `_MR` | 0.51 / **0.50** / 0.59 | same | "Book doesn't cover it" cut-off per language |
| `RAG_CEILING_ROMANIZED` | 0.0 | 0.0 | Retrieval off for Latin-script Hindi/Marathi |
| `RAG_PASSAGE_TOKEN_CAP` | 110 | 110 | Passage cut to its first sentences (0 = whole chunk) |
| `RAG_CONTEXT_TOKEN_BUDGET` | 4000 | 4000 | Max passage tokens per turn |
| `RAG_PIN_CORPUS_MAX_TOKENS` | 1500 | 1500 | Pin the whole book if it's this small (0 = never) |
| `RAG_DEDUP_CONTEXT` | true | true | Don't paste a passage twice in a session |
| `RAG_FOLLOWUP_REUSE` | true | true | Follow-ups reuse the last passage |
| Exercise slack (code) | 0.03 | — | How close an explanation must be to displace an exercise |
| Follow-up max words (code) | 8 | — | Longer messages are treated as new questions |
| `RAG_CHUNK_TARGET_CHARS` / `MAX` / `MIN` | 1200 / 2000 / 40 | same | Chunk size when uploading |
| `RAG_CHUNK_OVERLAP_CHARS` | 180 | 180 | Overlap between neighbouring chunks |
| `RAG_EMBED_BATCH_SIZE` | 16 | 16 | Chunks per embed call when uploading |
| `RAG_MAX_UPLOAD_MB` | 80 | 80 | Largest PDF |

### 14.3 Speech

| Parameter | In effect | What it does |
|---|---|---|
| `STT_INDIC_DIR` / `STT_INDIC_FILE` | models/indicconformer / model.onnx (fp32) | Hindi/Marathi STT |
| `STT_ENGLISH_DIR` | models/stt/sherpa-onnx-whisper-base.en | English STT |
| `STT_NUM_THREADS` | 4 | STT decode threads (the LLM is idle then) |
| `WARM_LANGUAGE` | English | Speech models warmed at backend start |
| `TTS_MODEL_DIR` | models/tts | Voice folders |
| `TTS_NUM_THREADS` | 2 | Synthesis threads (the LLM is still writing) |
| `TTS_SPEED` | **0.9** (`.env`; code 1.0) | Playback speed; slower hides writing gaps |
| Frontend STT constants | §5.2 | 16 kHz, RMS 0.012, 1.1 s silence, partials every 1.1 s |
| Frontend clip ramp | §11.2 | 18–28 → 20–40 → 24–52 → 30–64 chars |

### 14.4 Metrics and UI

| Parameter | Value | What it does |
|---|---|---|
| `METRICS_ENABLED` | true | Timing and retrieval trace per turn (panel and log line) |
| Groundedness minimum | 8 trigrams | Shorter answers are not scored |
| "Not drawn from your textbook" | groundedness < 0.05 | Label instead of a citation |

### 14.5 Outside the app (Ollama daemon and OS)

| Setting | Where | Recommendation |
|---|---|---|
| `OLLAMA_NUM_PARALLEL=1` | Ollama's environment | One cache slot, so the warm-up's cache is the one the first question uses |
| `OLLAMA_FLASH_ATTENTION` / `OLLAMA_KV_CACHE_TYPE=q8_0` | Ollama's environment | **Leave off**: measured slower on this CPU (44.1 ms/token vs 34.8) |
| Ollama process priority | set by `start.ps1` | AboveNormal (not High: High starves the UI) |
| Ollama auto-update | Ollama tray settings | **Turn off.** It silently upgraded 0.33.3 → 0.34.0 mid-session and stopped the server |

---

## 15. What we checked and what we chose

| Question | Options checked | Result | Chosen |
|---|---|---|---|
| Which LLM? | qwen2.5:1.5b, gemma3:1b, Navarasa, gemma2:2b | 1.5B and 1B: broken Hindi/Marathi | **gemma2:2b** |
| One model or one per language? | Split (small model for English) | Every language switch reloaded a model | **One model** |
| Which embedding model? | nomic-embed-text, paraphrase-multilingual, bge-m3 | nomic ranked wrong Hindi passages higher | **bge-m3** |
| Unload bge-m3 between questions? | keep_alive 0, 30 s, -1 | 0: +7.5 s reload per turn; 30 s: turns went up to 80 s | **Keep loaded** |
| Where do passages go? | System prompt (growing), system prompt (replaced), user turn | 27.7 vs 5.3 ms/token | **User turn** |
| Pin the whole book? | Pinned vs per-question | Pinned: 1.6–3.1 s prefill, but only for tiny corpora (7 chunks) | **Auto** when ≤ 1,500 tokens, else search |
| How many passages (k)? | 4, 3, 2, 1, none | k=4 1,404 tokens / 21 s prefill; k=2 841 / 11.9 s (09-04). Later k=2 vs 1: +2.9–4.9 s, 2nd passage useful 1/5 | **k=1** |
| How to shorten passages? | Best-matching sentences; first sentences | Best-matching dropped the facts and the model invented them | **First sentences, cap 110** |
| Rules every turn or in the persona? | Every turn; persona only; persona + reminder | Persona-only: 118–159-word answers | **Persona + short reminder** |
| Follow-ups? | Search on their words; rewrite the query; LLM classifier; reuse | Own-words search gave groundedness 0.00 | **Reuse** (word rule, no LLM call) |
| Ollama 0.34 cache regression? | Downgrade; llama.cpp flags; shorter answers; re-prime | Downgrade needs internet and gets undone by the next update | **Re-prime** |
| Threads? | 2, 3, 4 | 43.2 / 39.7 / 34.8 ms/token | **4** |
| Flash attention + q8 cache? | On / off | On: slower (44.1 ms/token) | **Off** |
| PDF extraction? | pypdf, PyMuPDF | pypdf corrupted 100% of Hindi | **PyMuPDF** |
| Legacy-font Hindi books? | Refuse upload; ask for Unicode copies; GPL converters; our own | Rule: never block the uploader; NCERT has no Unicode copy | **Our own converter** |
| Hindi ceiling? | 0.58, 0.50 | 0.58 let 4/10 off-syllabus through | **0.50** |
| Search scope? | Class only; class + subject + medium | Cross-lingual bge-m3 pulled other books | **Class + subject + medium** |
| Exercises in the results? | Drop them; unbounded demotion; bounded (0.03) | Dropping loses story lines; unbounded promoted junk | **Bounded demotion** (not strong enough yet, see §19) |
| Groundedness instruction? | "Answer the question… never mention the text" vs "Answer using the facts in the text…" | 0.179 → 0.266 | **"Use the facts"** |
| Hindi STT? | Chrome Web Speech, IndicConformer int8, fp32 | Chrome not offline here; int8 2× errors | **IndicConformer fp32** |
| English STT? | Browser Web Speech, Moonshine, Whisper base.en | Browser uses Google's servers | **Whisper base.en** (Moonshine also supported by file layout) |
| TTS? | Browser MMS, Parler, IndicVoice, browser speechSynthesis, Piper | MMS ~15 s/sentence; Parler too big | **Piper (backend)** |
| TTS gaps? | Pre-buffer clips; filler audio; clip ramp | Pre-buffer delays the first word; filler rejected by the user | **Clip ramp** |
| "Good question" filler audio? | Built and tested | User: reduce real latency instead | **Removed** |

---

## 16. What improved, and by how much

| Area | Before | After | Measured how |
|---|---|---|---|
| First word, new textbook question | 47–54 s | 4.3–7.1 s | Live timing panel |
| Prefill, new textbook question | 43–50 s | ~4–6 s (8.2 s after the layout fix alone) | Backend log |
| Next-turn prefill (after an answer) | 5.3–6.0 s | 2.46 s median | Controlled test, 4 rounds |
| First word, follow-up | 7.0–7.4 s | 2.4–3.0 s | Live |
| New rule tokens per Hindi turn | 56 | 10 | Token count |
| Hindi text corruption (broken clusters / 100 chars) | 4.45–7.28 | 0.15–0.47 | Integrity check |
| Legacy-font book Devanagari share | 0% | 98.4% | Integrity check |
| Hindi best-hit distance (median) | 0.53–0.57 | 0.44 | Retrieval trace |
| Off-syllabus shown as textbook | 4/10 | 0/10 | 22-question check |
| Groundedness (median) | 0.179 | 0.266 | 14-question A/B |
| Key fact present | 9/14 | 10/14 | Same A/B |
| Silence after first clip | 5.0–12.2 s | 1.5–1.9 s | **Simulated** |
| Gap between clip 1 and clip 2 | 1.4–9.6 s | 0.4–0.5 s | **Simulated** |
| Unused files in the frontend `public/` folder | 139 MB | ~20 KB | Folder size |
| Backend tests | — | 154 passing | pytest |

---

## 17. Pitfalls

**Latency**
- **Background CPU load ruins everything.** An upload, a benchmark, or Google Meet on a 2-core
  laptop turns 6 s into 43–56 s and a 1 s STT decode into 175 s. Upload books outside lessons.
  For demos, share a window rather than running heavy video effects, and expect slower answers.
- **Ollama auto-update** silently upgrades and stops the server ("Ollama isn't responding").
  Check `%LOCALAPPDATA%\Ollama\upgrade.log`. Re-measure latency after any version change: the cache
  behaviour is engine-specific.
- **Anything that changes the top of the prompt** throws the cache away (§9.3).
- **Heat:** up to 2.4× on identical work. Compare A/B arms interleaved, never back to back.

**Configuration**
- **Misspelled `.env` names are ignored silently** (pydantic `extra="ignore"`). Check the field name
  in `config.py`.
- **`num_predict: 0` in Ollama means unlimited**, not "generate nothing". The re-prime uses 1.
- **Warm-up and chat must send identical `num_ctx`/`num_thread`**, or Ollama reloads the model.
- **`NUM_CTX` overflow drops the system prompt** from the front without an error. Answers then
  quietly ignore the rules. Raise `NUM_CTX` if you raise `RAG_TOP_K` or history.

**Content**
- **Scanned PDFs have no text.** They're refused with an OCR hint (e.g. `Class-X-Hindi Grammar.pdf`,
  `Hindi Vyakaran & Rachna.pdf`).
- **Other legacy fonts** (NeoMitra/NeoNatraj from SCERT Telangana) are not mapped. They upload with
  a warning and retrieve poorly.
- **Exercises outrank explanations** when they repeat the student's words (§7.3).
- **Class labels must match what students pick.** A book uploaded as Class 6 is invisible from Class 10.
- **Romanized Hindi gets no textbook** (retrieval deliberately off).
- **The follow-up rule is a word list:** a short *new* question containing "this" or "यह" is treated
  as a follow-up.

**Operations**
- **`start.ps1` stops the backend when its window closes.** Keep it open; Ctrl+C to stop.
  (`launch.mjs` was fixed to stay alive when it reuses an already-running frontend.)
- **Sessions live in memory:** restarting the backend forgets conversations (the library is kept).
- **One lesson at a time.** Ollama caches one prompt; two tabs evict each other's cache.

---

## 18. Scale

**More PDFs**
- **Question latency barely changes.** The prompt holds 1 passage regardless of library size. Only
  the search grows, and search took milliseconds at the sizes measured (3–8 ms vector scan, 10–30
  ms FTS5, measured on a smaller library; not re-timed at 3,573 chunks). The class partition means
  a question scans only its own class.
- **Accuracy can get worse** as more books share a class + subject: more near-duplicates and more
  exercises competing for the single slot.
- **Upload time grows linearly:** ~3–5.5 s per page on this laptop, one book at a time.
- **Disk:** ~33 MB for 3,573 chunks (≈ 9–10 KB per chunk, mostly the 4 KB vector plus text and index).
  A full K-12 set of a few thousand pages stays in the hundreds of MB.
- **Build centrally:** `library.db` is one file. It can be built on a fast machine and copied to
  every laptop, which avoids uploading on 15 W CPUs.

**More languages**

| Layer | What's needed |
|---|---|
| STT | The IndicConformer export covers 8 languages (hi, mr, bn, gu, kn, as, brx, ks); Tamil and Telugu need a different export |
| TTS | Piper has hi, mr, te, ml, bn, ne, ur; none for ta, kn, gu, pa, or, as |
| LLM | gemma2:2b's quality outside Hindi/English/Marathi is untested |
| Retrieval | Each language needs its own measured ceiling (Marathi 0.59 is from the old, corrupted text) |

**More users**
- The design is **one student per laptop**. Ollama runs one cache slot; a second concurrent user
  would evict the first user's cache and double CPU load.
- A classroom server would need a GPU box. That breaks the "one device, offline" constraint and is
  out of scope.

**Better hardware (the 16 GB targets)**
- More RAM: room for a larger `NUM_CTX` (longer lessons, k=2 without overflow).
- Newer 4-core CPUs (8th Gen+): faster prefill and decode. Re-measure `OLLAMA_NUM_THREAD` there
  (set it to the new optimum, likely the physical core count or a bit more).
- **None of this has been measured yet.**

---

## 19. Where we are, and what we can use next

**Status (2026-09-11)**

| Goal | Target | Now | Met? |
|---|---|---|---|
| First audio, follow-up | 3–4 s | ~4–5 s (first word 2.4–3.0 s) | Nearly |
| First audio, new textbook question | 7–8 s accepted | ~6–9 s (estimate; first word 4.3–7.1 s) | Mostly |
| Groundedness | 0.40–0.45 | 0.266 | **No** |
| Citations honest | No false "from textbook" | 0/10 false | Yes |
| Hindi books readable | Clean Devanagari | PyMuPDF + converter | Yes (not scans, not NeoMitra) |
| Speech gaps | < 1 s | 0.4–0.5 s (simulated) | Likely; verify in browser |
| Tests | Green | 154 passing, frontend type-check clean | Yes |
| Committed | — | **No** | Waiting for review |

**Next, in order of value (measured options first)**

1. **Stronger exercise demotion.** Make the one passage an explanation page. It targets the main
   groundedness blocker and costs **0 s**. Test on a quiet machine with the 6 questions in §7.3.
2. **Passage cap 110 → 180 tokens.** More facts per passage, ~+2.5–3 s. A/B parked; run it quietly.
3. **Measure on the 16 GB targets.** Latency, threads, and whether k=2 becomes affordable.
4. **Browser-measured speech gaps** to confirm the simulated numbers.
5. **Recalibrate the Marathi ceiling** on clean Marathi books.
6. **OCR for scanned books** (an offline OCR step before upload; not built).
7. **Transliterate romanized Hindi to Devanagari** before search, so "gharshan bal" can use the book.
8. **Map NeoMitra/NeoNatraj fonts** if those books are needed.

**Ideas not tested (don't assume they work)**
- A different small model with better Hindi (any candidate must beat gemma2:2b on Hindi quality first).
- A smaller IndicConformer (int8 is 2× worse; a better quantisation is unknown).
- Passing the chunk *after* the best hit when it continues the same explanation.

---

## 20. Running it, and where to look

**Setup (once, needs internet):**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1
ollama pull gemma2:2b
ollama pull bge-m3
```

`setup.ps1` installs the frontend, desktop and backend dependencies, creates the `.env` files, and
downloads IndicConformer (~470 MB), Whisper base.en (~145 MB) and the Piper voices (~200 MB). It's
safe to re-run. macOS/Linux: `scripts/setup.sh`.

**Start (every time, offline):**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start.ps1
```

This checks Ollama, sets its priority, starts the backend (waits for `/health`), then opens the app
window. Keep the window open; Ctrl+C stops everything.

**Where to look**

| To see… | Look at |
|---|---|
| Per-answer timing, passage, distance, groundedness | **Timing & retrieval** under each answer |
| Backend per-turn line (`turn … retrieval … prefill … decode …`), re-prime lines | `backend.out.log` / `backend.err.log` in the repo root |
| Ollama cache and checkpoint behaviour | `%LOCALAPPDATA%\Ollama\server.log` |
| Ollama silent upgrades | `%LOCALAPPDATA%\Ollama\upgrade.log` |
| Retrieval recall and ceilings | `scripts/evaluate_retrieval.py` with `scripts/golden_set.json` (42 questions) |
| Backend tests | `apps/backend/.venv/Scripts/python -m pytest` (install `requirements-dev.txt` first) |

**Key files**

| File | Job |
|---|---|
| `apps/backend/app/config.py` | Every setting, with the measurement behind each value |
| `apps/backend/app/routers/chat.py` | A turn: retrieval path, prompt assembly, streaming, re-prime, metrics |
| `apps/backend/app/services/tutor.py` | Persona, rules, the student's turn message |
| `apps/backend/app/services/rag/retrieval.py` | Search, gate, fusion, exercise order, trimming, pinning |
| `apps/backend/app/services/rag/ingest.py` / `pdf_text.py` / `legacy_hindi.py` / `chunking.py` | Upload pipeline |
| `apps/backend/app/services/ollama_client.py` | Chat, stream, warm, prime |
| `apps/backend/app/services/stt.py` / `tts.py` | Speech engines |
| `apps/frontend/src/hooks/useTutorSession.ts` | The turn orchestrator: STT → chat stream → clips → TTS |
| `apps/frontend/src/pages/StartPage.tsx` | Lobby: choices from the library, readiness, priming |
| `docs/EXPERIMENT-LOG.md` | Every experiment: hypothesis, numbers, what failed |
