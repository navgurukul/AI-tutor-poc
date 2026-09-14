# Offline AI Tutor — Experiment Log (since commit `f9f16ad`)

Everything changed on branch `mintplex-piper` after the last commit (`f9f16ad` "TTS ON backend"),
written as one entry per experiment: what we tried, what worked, what failed, and the numbers.
Work dates: 2026-09-07 → 2026-09-14. Nothing here is committed yet.

**Config for Ella and offline STS**

**HP ZBook 15 G5/G6:**
Processor – Intel Core i5/i7, 8th/9th Gen, 16 GB RAM, 256 GB storage.

**HP EliteBook 840 G3/G4/G5/G6/G7:**
Processor – Intel Core i5/i7, 6th/7th/8th/10th Gen, 16 GB RAM, 256 GB storage.

> **Every number below was measured on the dev box, which is weaker than both configs above:**
> Intel Core i7-6600U (6th Gen, **2 physical cores** / 4 threads, 15 W — the EliteBook 840 G3 class
> CPU) with **8 GB RAM**, Windows 10 Pro 19045, CPU only, fully offline at question time.
> The 16 GB / 8th–10th Gen targets should do at least as well; that has **not** been measured.

## Contents

| # | Experiment | Verdict |
|---|---|---|
| EXP-001 | Prompt layout for the KV cache (excerpts into the turn) | Adopt |
| EXP-002 | Ollama 0.34 cache checkpoints → background re-prime | Adopt |
| EXP-003 | Reply rules moved into the cached persona | Adopt (switchable) |
| EXP-004 | Follow-up questions reuse the previous passage | Adopt |
| EXP-005 | Hindi PDF extraction: pypdf → PyMuPDF | Adopt |
| EXP-006 | Legacy Hindi fonts (Walkman-Chanakya/Kruti) → Unicode on upload | Adopt |
| EXP-007 | Retrieval scope, relevance gate and citation honesty | Adopt |
| EXP-008 | Groundedness: per-turn instruction, k=2, bigger passages | Partly adopted / partly parked |
| EXP-009 | Speech output: clip ramp, voice warm-up, retry | Adopt |
| EXP-010 | Library & lobby UI (class / subject / medium, multi-upload) | Adopt |
| EXP-011 | Things we tried that failed or were rejected | Reject (recorded so they are not retried) |
| EXP-012 | Clean-up: stale code, libraries and files removed | Done |
| EXP-013 | First question after a cold start: warm the embedding model | Running (fix in, not yet measured) |
| EXP-014 | Hindi transcripts came back with every word doubled | Running (three causes fixed, not yet confirmed) |
| EXP-015 | Answers inaudible while the backend synthesised every clip | Running (failure now reported, cause pending) |

How the measurements were taken: one-off interleaved A/B scripts run straight against Ollama
(removed after use — the method is described in each entry), `scripts/evaluate_retrieval.py` +
`scripts/golden_set.json` for retrieval recall/calibration, and the per-turn timing panel in the
app (Timing & retrieval), which is the same data the backend logs as
`turn …ms | retrieval … | prefill … | decode …`.

**One rule that every measurement here depends on:** this box swings up to **2.4×** on identical
work with temperature, and anything else using the CPU (a library upload, a benchmark, Google Meet)
wrecks latency — on 2026-09-11 a background A/B pushed a normal ~6 s turn to 43–56 s. Compare
numbers only when nothing else is running, and interleave A/B arms instead of running them back to back.

---

# EXP-001 — Prompt layout for the KV cache: excerpts into the turn

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-09 | **Date closed:** 2026-09-10 | **Status:** Worked
**Device tested on:** 8 GB Windows laptop (dev machine, i7-6600U)
**Related experiments:** EXP-002, EXP-003, EXP-011

## 1. Context
After uploading a real corpus (18 books / 756 chunks) the first-token time collapsed to **47–54 s**
(prefill 43–50 s). Ollama only reuses its cache when a new prompt *extends* the previous one; the
retrieved excerpts sat inside the **system prompt**, so every question changed the front of the
prompt and forced a full re-read.

## 2. Hypothesis
If the excerpts move out of the system prompt into the student's own turn, the persona + history
stay a stable, cacheable prefix and each turn only pays for its new tokens, cutting prefill from
~45 s to under ~10 s.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Grow the excerpts inside the system prompt ("accumulate") | Measured 27.7 ms/token on turn 2 vs 5.3 ms/token with excerpts in the turn — it forks the prompt every time |
| Pin the whole corpus in the prompt | Only works for tiny books; 756 chunks ≈ 155,000 tokens. Kept as automatic mode when a selection fits `RAG_PIN_CORPUS_MAX_TOKENS` (1500) |
| Smaller / faster model | gemma3:1b was 2× faster but incoherent in Hindi (EXP-011) |

## 4. What we did — step by step
1. `tutor.build_turn_message()` — the turn is `[excerpts] + question + short rules`; the persona holds `RETRIEVAL_RULE` once.
2. `chat.py` stores the *augmented* user message in the session, so the replayed history is byte-identical next turn.
3. Passage dedup (`RAG_DEDUP_CONTEXT=true`): a chunk is pasted once per session; `session.remember_chunks()`.
4. Passages trimmed to their **first sentences** (head), cap `RAG_PASSAGE_TOKEN_CAP=110`; `RAG_TOP_K` 2 → 1.
5. Persona trimmed 575 → 436 tokens; answer length rules raised (85 words Hindi / 110 English, "4–5 sentences").
6. Lobby warm-up primes the same prefix before the student asks; the chat page reuses that primed session.

**Environment**
- Model / library: gemma2:2b (Ollama 0.33.3 at the time), bge-m3 embeddings, sqlite-vec 0.1.9
- Runtime: `OLLAMA_NUM_THREAD=4`, `NUM_CTX=4096`, `MAX_HISTORY_MESSAGES=20`
- Hardware/OS: i7-6600U, 8 GB, Windows 10 19045
- Baseline: excerpts in the system prompt, same corpus

## 5. What we measured
| Metric | Baseline | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Cold start | not measured | not measured | — | — |
| End-to-end latency (first token) | 47–54 s | 9.4 s | 5–6 s | Partly (see EXP-002/003) |
| Prefill | 43–50 s | 8.2 s | — | — |
| Peak RAM | not measured | not measured | — | — |
| Package size | unchanged | unchanged | — | — |
| Accuracy / WER | — | — | — | — |

Measured from the in-app timing panel and backend log, Hindi questions, warm turns, single runs
interleaved by hand. Cost model derived from interleaved prefill A/B runs: prefill ≈ new tokens × ~50 ms + total tokens × ~2 ms (Ollama 0.33).

## 6. What worked
Moving the only per-question content to the end of the prompt. The mechanism is prefix reuse:
everything before the new turn is identical to the previous request, so Ollama skips it.

## 7. What didn't work
**Failure 1 — accumulating excerpts in the system prompt**
- Symptom: turn-2 prefill stayed at ~28 ms/token.
- What we tried: growing a stable, append-only excerpt list in the system prompt.
- Root cause: anything that changes before the history forks the cached prefix.
- Dead end.

**Failure 2 — picking the sentences that best match the question when trimming passages**
- Symptom: asked about संज्ञा's types, the kept sentence was "there are three main types" and the one naming them was dropped; the model invented three types.
- Root cause: word-overlap prefers topic sentences that carry no content. Replaced with keeping the head of the passage.
- Dead end.

**Failure 3 — React StrictMode discarded the primed session**
- Symptom: repeated ~22 s first turns right after the lobby.
- Root cause: a "consume once" ref was spent on StrictMode's double effect run. Fixed by comparing against the memoised profile.

## 8. Error logs
```
[turn] prefill 43,000–50,000 ms with excerpts in the system prompt (756-chunk corpus)
excerpts grown in the system prompt : 27.7 ms/token on turn 2
excerpts attached to the user turn  :  5.3 ms/token on turn 2
```

### 9. Conclusion and next step
Supported. Prompt layout, not the model, was the biggest latency lever; every later latency gain builds on it.
- [x] Verdict: adopt
- [x] Follow-up experiment: EXP-002 (after the Ollama upgrade), EXP-003
- [x] Code or docs updated: `tutor.py`, `chat.py`, `sessions.py`, `retrieval.py`, `config.py`
- [ ] Shared with team on:

---

# EXP-002 — Ollama 0.34 cache checkpoints → background re-prime after every answer

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-10 | **Date closed:** 2026-09-11 | **Status:** Worked
**Device tested on:** 8 GB Windows laptop (dev machine)
**Related experiments:** EXP-001, EXP-003

## 1. Context
On 2026-09-10 22:38 the Ollama tray app **silently auto-updated 0.33.3 → 0.34.0** and stopped the
server (start.ps1: "Ollama isn't responding"). After the upgrade, follow-up turns cost more than
the cost model predicted: each turn's prefill matched re-reading the *previous answer* too.

## 2. Hypothesis
If Ollama 0.34 cannot reuse the tokens it generated, then sending, right after each answer, a
request whose prompt ends exactly at that answer will create a cache point there and cut the
next turn's prefill by the answer's length (≈2.5–5 s).

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Downgrade Ollama | Needs internet and a manual install on every device; the next auto-update would undo it |
| Change llama.cpp flags (e.g. full SWA cache) | Ollama does not expose them |
| Shorter answers | Reduces the cost but also teaching quality; does not remove the cause |

## 4. What we did — step by step
1. Proved the cause from `%LOCALAPPDATA%\Ollama\server.log`: gemma2 uses sliding-window attention; llama.cpp's server can only resume from a **checkpoint**, and saves one only at the end of each *prompt*.
2. Controlled test (same prompt, 3 rounds): next turn after a generated reply 5.3–5.4 s; identical repeat 0.42–0.48 s; changed last question 5.4–6.0 s.
3. Built `ollama_client.prime()` (prefill + 1 token, same load options so no reload) and `chat._reprime_after_reply()`: after each answer, prime `history(max_history_messages − 1)` ending on the reply.
4. `num_predict=0` is **not** "generate nothing" in Ollama (it ran until the model stopped) — the prime uses 1.
5. Setting `OLLAMA_REPRIME_AFTER_REPLY=true`; tests in `tests/test_reprime.py` pin the window rule.

**Environment**
- Ollama 0.34.0 (llama.cpp server engine), gemma2:2b
- Baseline: same prompt without the prime

## 5. What we measured
| Metric | Baseline | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Next-turn prefill (controlled, 4 rounds) | 5.3–6.0 s | **2.46 s** median | < 3 s | Yes |
| First token, follow-up (live, user screenshots) | 7.0–7.4 s | 2.4–3.0 s | 3–4 s | Yes |
| First token, new textbook question (live) | 9.4–9.9 s | 4.3–7.1 s | 5–6 s | Mostly |
| Peak RAM | not measured | not measured | — | — |

## 6. What worked
The prime moves the re-read of the answer into the 15–25 s while the answer is being spoken. If the
student asks earlier, their request queues behind work it needed anyway — never slower than before.

## 7. What didn't work
**Failure 1 — Ollama auto-update**
- Symptom: server stopped mid-session; a library rebuild was cut off and left a half-embedded book.
- Root cause: tray-app updater (`auto_update_enabled=1`).
- Parked: recommended turning auto-update off in Ollama settings (user's install, not changed by us).

## 8. Error logs
```
slot   operator(): id  0 | task 1080 | forcing full prompt re-processing due to lack of cache data (likely due to SWA or hybrid/recurrent memory, see https://github.com/ggml-org/llama.cpp/pull/13194#issuecomment-2868343055)
slot print_timing: id  0 | task 1080 | prompt processing, n_tokens =    483, progress = 0.99, t =  16.86 s / 28.66 tokens per second
slot create_check: id  0 | task 1080 | created context checkpoint 1 of 32 (pos_min = 0, pos_max = 482, n_tokens = 483, size = 24.533 MiB)

time=2026-09-10T22:38:31.183+05:30 level=INFO source=updater_windows.go:155 msg="starting upgrade" installer=C:\Users\Admin\AppData\Local\Ollama\OllamaSetup.exe args="[/CLOSEAPPLICATIONS /LOG=upgrade.log /FORCECLOSEAPPLICATIONS /SP /NOCANCEL /SILENT /VERYSILENT /SUPPRESSMSGBOXES]"
ERROR:    [Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000): [winerror 10048] only one usage of each socket address (protocol/network address/port) is normally permitted

re-prime 1812ms | prefill 1766ms (650 tok) -- next turn resumes after the reply
```

### 9. Conclusion and next step
Supported. Re-verify after any Ollama upgrade — the cache behaviour is engine-specific.
- [x] Verdict: adopt
- [ ] Follow-up experiment: re-measure on the 16 GB targets
- [x] Code or docs updated: `ollama_client.py`, `chat.py`, `config.py`, `tests/test_reprime.py`
- [ ] Shared with team on:

---

# EXP-003 — Reply rules moved into the cached persona (short reminder per turn)

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-11 | **Date closed:** 2026-09-11 | **Status:** Worked (small sample)
**Device tested on:** 8 GB Windows laptop
**Related experiments:** EXP-001, EXP-008

## 1. Context
Every turn re-sent the reply rules (plain sentences, word budget, no closing question, reply
language). They are new tokens every turn: measured **56 real tokens** on a Hindi textbook turn,
**47** in English.

## 2. Hypothesis
If the rules live once at the end of the cached persona and each turn keeps only a short reminder,
each textbook question saves ~45 tokens ≈ 1.5–1.7 s of prefill with no loss in compliance.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Rules in the persona with **no** reminder | Answers ran long (103–159 words) and one missed its key fact |
| Keep rules on every turn | Costs ~1.5–1.7 s per textbook question |
| Shorter passages instead | Hurts groundedness (EXP-008) |

## 4. What we did — step by step
1. Quality check, 3 arms × 7 questions (5 Hindi, 2 English with passages), fixed seed, interleaved: A rules every turn / B rules in persona only / C persona + short reminder.
2. Adopted C: `tutor._persona_reply_rules()` appended to the persona; the turn ends with "Reply only in Hindi (Devanagari)." (Hindi) or "Under 110 words." (English).
3. Setting `TUTOR_RULES_IN_PERSONA=true` (set `false` to restore); `tests/test_turn_rules.py`.

## 5. What we measured
| Metric | A (before) | C (after) | Target | Met? |
| --- | --- | --- | --- | --- |
| New rule tokens per Hindi textbook turn | 56 | 10 | fewer | Yes |
| Key fact present | 5/7 | 7/7 | ≥ A | Yes |
| Answered in the right language | 7/7 | 7/7 | 7/7 | Yes |
| Talked about "the text" | 0 | 0 | 0 | Yes |
| Ended with a question | 0 | 1 | 0 | No (1 case) |

The run was stopped at 7 of 11 questions because it competed with live testing; small sample.

## 6. What worked
Cached tokens are nearly free; the one rule gemma2 drops first without a reminder (reply language, or length in English) stays at the end of the prompt, where this model weights instructions most.

## 7. What didn't work
**Failure 1 — rules in persona with no reminder (arm B)**
- Symptom: 118–159-word answers; one missing key fact.
- Root cause: gemma2:2b follows the end of the prompt much more than the start.
- Dead end.

## 8. Error logs
```
Hindi: per-turn rules 34 real tokens (with passage 56) | tail 10 tokens
English: per-turn rules 25 real tokens (with passage 47) | tail 7 tokens
[B rules in persona        ] fact=True  ... words=159 ground=0.212 | What is a data flow diagram?
```

### 9. Conclusion and next step
Supported on a small sample; re-check on more Hindi textbook turns once Hindi books are back in the library.
- [x] Verdict: adopt (switchable)
- [ ] Follow-up experiment: full 11-question run with Hindi passages, on a quiet machine
- [x] Code or docs updated: `tutor.py`, `config.py`, `tests/test_turn_rules.py`
- [ ] Shared with team on:

---

# EXP-004 — Follow-up questions reuse the previous passage

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-11 | **Date closed:** 2026-09-11 | **Status:** Worked (unit-tested; live latency not isolated)
**Device tested on:** 8 GB Windows laptop
**Related experiments:** EXP-002, EXP-007

## 1. Context
A follow-up like "इसका एक उदाहरण दीजिए।" was searched on its own words; it matched an unrelated
passage and the answer was nonsense (groundedness 0.00), and the new passage cost prefill.

## 2. Hypothesis
If a short message that points back ("इसका / यह / this / it / उदाहरण…") keeps the previous answer's
passage instead of searching, follow-ups become cheaper and stay grounded.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Rewrite the follow-up with the previous question before searching | Extra embedding + more prompt tokens; still can pick a different passage |
| An LLM call to classify follow-ups | Costs seconds of prefill on this CPU |

## 4. What we did — step by step
1. `chat._is_followup()`: ≤ 8 words and contains a back-reference word (Hindi/Marathi/English list).
2. `session.last_hit_ids` records the passages each answer used; a follow-up reuses them with no new search and nothing new pasted (it is already in the conversation). Citations and groundedness still see it.
3. Setting `RAG_FOLLOWUP_REUSE=true`; `tests/test_followup.py` (13 cases).

## 5. What we measured
| Metric | Baseline | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Follow-up search + new passage tokens | ~0.3 s + ~70–110 tokens | 0 | 0 | Yes |
| Follow-up grounded in the right passage | no (0.00 case) | yes (by construction) | yes | Yes |

## 6. What worked
The passage the student means is already a few messages up; reusing it is both correct and free.

## 7. What didn't work
Nothing yet. Known limit: a short *new* question containing "this"/"यह" is treated as a follow-up.

## 8. Error logs
```
turn ... | hi best 0.467 headroom +0.033 grounded 0.00   ("इसका एक उदाहरण दीजिए।", before the change)
```

### 9. Conclusion and next step
- [x] Verdict: adopt
- [ ] Follow-up experiment: measure live follow-up latency on a quiet machine
- [x] Code or docs updated: `chat.py`, `sessions.py`, `config.py`, `tests/test_followup.py`
- [ ] Shared with team on:

---

# EXP-005 — Hindi PDF extraction: pypdf → PyMuPDF

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-10 | **Date closed:** 2026-09-10 | **Status:** Worked
**Device tested on:** 8 GB Windows laptop
**Related experiments:** EXP-006, EXP-007

## 1. Context
Days of Hindi prompt/model/retrieval tuning had not fixed poor Hindi answers. The stored chunk text
itself had never been checked.

## 2. Hypothesis
If the Hindi text is extracted with PyMuPDF instead of pypdf, the Devanagari becomes correct and Hindi
retrieval distances and passage quality improve without touching the model.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Keep pypdf, repair text afterwards | The corruption is a font-map problem, not recoverable by rules |
| OCR every Hindi book | Slow on this CPU and less accurate than real text |
| pdfminer.six | Not needed once PyMuPDF measured clean |

## 4. What we did — step by step
1. Measured "impossible" Devanagari (a vowel sign starting a word, two viramas in a row, orphaned vowel signs): **100% of the Hindi corpus was corrupt** under pypdf.
2. Switched extraction to `pymupdf==1.28.2` (`pdf_text.extract_pages`).
3. Collapsed doubled vowel signs (`न्यााय` → `न्याय`), which PyMuPDF produced on one book.
4. Dropped duplicate chunks (pypdf had returned some text layers twice — that was the "lead over runner-up 0.001").
5. Rebuilt the library (18 books → 599 clean chunks).

## 5. What we measured
| Metric | pypdf | PyMuPDF | Target | Met? |
| --- | --- | --- | --- | --- |
| Broken clusters per 100 Devanagari chars | 4.45–7.28 | 0.15–0.47 | < 1.5 | Yes |
| Duplicate chunk groups | 42 | 0 | 0 | Yes |
| Hindi best-hit distance (median) | 0.53–0.57 | 0.44 | lower | Yes |
| English text | — | character-identical | same | Yes |

## 6. What worked
PyMuPDF follows the fonts' ToUnicode maps; pypdf emitted glyphs in drawing order through the wrong table.

## 7. What didn't work
**Failure 1 — pypdf on NCERT Hindi**: symptom above; root cause = ignored subset-font ToUnicode maps. Dead end (pypdf removed in EXP-012).

## 8. Error logs
```
pypdf    "किरन ने ्ूसरी ्ुकनया में जाने िी िात कयों िही होगी?"
pymupdf  "किरन ने दूसरी दुनिया में जाने की बात कयों कही होगी?"
ehve102  doubled-matra= 529  per100=6.89  e.g. बााहर लंबाा-चौड़ाा मैैदाान थाा।
```

### 9. Conclusion and next step
Supported — the Hindi "model quality" problem was largely a data problem.
- [x] Verdict: adopt
- [x] Code or docs updated: `pdf_text.py`, `chunking.py`, `requirements.txt`
- [ ] Shared with team on:

---

# EXP-006 — Legacy Hindi fonts (Walkman-Chanakya / Kruti Dev) → Unicode on upload

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-11 | **Date closed:** 2026-09-11 | **Status:** Worked
**Device tested on:** 8 GB Windows laptop
**Related experiments:** EXP-005

## 1. Context
The Class 10 Hindi Geography book (समकालीन भारत-2) matched no Hindi question (best hit 0.56–0.64 vs
ceiling 0.50). Its text had **0 Devanagari characters**: NCERT typesets Hindi Social Science in the
8-bit **Walkman-Chanakya905** font — even the 2024-25 reprint downloaded from ncert.nic.in.

## 2. Hypothesis
If spans set in a legacy font are converted to Unicode during upload, the book becomes searchable
and answers can cite it, with no user action and no upload blocked.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Refuse such uploads | User rule: never block the uploader |
| Ask for Unicode copies | NCERT does not publish them |
| GPL-3.0 converters (IIT Delhi Assistech, LTRC kru2uni) | Would put GPL obligations on the project; we wrote our own from the character correspondences |

## 4. What we did — step by step
1. Identified the fonts with PyMuPDF (`get_fonts`): Walkman-Chanakya905 Normal/Bold/Italic + 901.
2. Built the glyph table from the book (128 distinct glyphs), checking each in context.
3. `app/services/rag/legacy_hindi.py`: longest-match table; moves ि after its consonant cluster and the reph र् before its syllable; handles Chanakya's hook glyphs for क/फ.
4. `pdf_text._page_text()` converts only spans whose font is legacy (English/Arial untouched); other pages take the old path.
5. Uploads never refuse for text quality: broken or unconverted Hindi is stored **with a warning**.
6. 45 real phrases from the book pinned in `tests/test_legacy_hindi.py`.

## 5. What we measured
| Metric | Before | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Devanagari share of the book's letters | 0% | 98.4% | > 90% | Yes |
| Broken clusters per 100 chars | n/a | 0.06 | < 1.5 | Yes |
| Key words found | 0 | काली मृदा 7, बहुउद्देशीय 12, कृषि 156, संसाधन 210 | > 0 | Yes |

## 6. What worked
The encoding is deterministic; per-span font names make detection exact rather than guessed.

## 7. What didn't work
**Failure 1 — NeoMitra/NeoNatraj fonts (SCERT Telangana)**: a different legacy encoding (`∫Á…b~-TÁå`); not mapped. Parked — such books upload with a warning.

## 8. Error logs
```
lkekftd foKku / ledkyhu / Hkkjr&2 / d{kk 10 osQ fy, Hkwxksy   (= सामाजिक विज्ञान / समकालीन / भारत-2 / कक्षा 10 के लिए भूगोल)
jhss101: 12 pages | Devanagari 0, Latin 18594 | "gekjs i;kZoj.k eas miyCèk izR;sd oLrq"
best hit 0.643 is beyond the hi ceiling 0.50
```

### 9. Conclusion and next step
- [x] Verdict: adopt
- [ ] Follow-up experiment: re-upload the Geography book and check live groundedness
- [x] Code or docs updated: `legacy_hindi.py`, `pdf_text.py`, `ingest.py`, tests
- [ ] Shared with team on:

---

# EXP-007 — Retrieval scope, relevance gate and citation honesty

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-10 | **Date closed:** 2026-09-11 | **Status:** Worked
**Device tested on:** 8 GB Windows laptop
**Related experiments:** EXP-005, EXP-008

## 1. Context
Answers showed "From your textbook" for topics the book does not cover, and search only filtered by class.

## 2. Hypothesis
If search is scoped to the lobby's class + subject + medium, and the Hindi relevance cut-off is
re-measured on clean text, off-syllabus questions stop getting textbook citations without losing real ones.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Keep the 0.58 Hindi cut-off | Tuned on corrupt text; let 4/10 off-syllabus questions through |
| Drop exercises from search | They sometimes hold the lesson's sentences; reordered instead |
| Always show the citation | A page number on an answer that ignored the page reads as false proof |

## 4. What we did — step by step
1. Vector and keyword search filtered by grade, subject and medium; medium matched in any spelling ("Hindi"/"hi"/"").
2. Hindi ceiling `RAG_CEILING_HI` 0.58 → **0.50** from 12 answerable vs 10 off-syllabus questions.
3. Fill-in exercises yield to an explanation within 0.03 distance (never dropped).
4. Label becomes "Not drawn from your textbook" when groundedness < 0.05.

## 5. What we measured
| Metric | Before | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Off-syllabus questions shown as textbook | 4/10 | 0/10 | 0 | Yes |
| Answerable questions kept | 12/12 | 11/12 | 12/12 | Almost (bare title "न्याय की कुर्सी क्या है?" at 0.532) |

## 6. What worked
On clean text the two groups separate (answerable 0.27–0.47, off-syllabus 0.53–0.61).

## 7. What didn't work
**Failure 1 — unbounded exercise demotion**: would have promoted "SI unit of length" (0.371) above the linear-motion activity (0.364). Fixed by the 0.03 bound.

## 8. Error logs
```
ON  : min 0.273  median 0.391  max 0.532
OFF : min 0.532  median 0.580  max 0.610
current ceiling 0.58 -> 0 false-reject, 4 false-accept
```

### 9. Conclusion and next step
- [x] Verdict: adopt
- [x] Code or docs updated: `store.py`, `retrieval.py`, `chat.py`, `config.py`, `ChatBubble.tsx`, tests
- [ ] Shared with team on:

---

# EXP-008 — Groundedness: per-turn instruction, k=2, bigger passages

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-10 | **Date closed:** open | **Status:** Partly worked / parked
**Device tested on:** 8 GB Windows laptop
**Related experiments:** EXP-003, EXP-007

## 1. Context
Groundedness (share of the answer's word sequences found in the passage) sat around 0.07–0.24; target 0.40–0.45.

## 2. Hypothesis
If the per-turn instruction tells the model to *use* the passage (not just "never mention it"),
groundedness rises with no latency cost; more passage text would raise it further at a latency cost.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| k=2 (two passages) | +2.9–4.9 s per textbook turn; only 1 of 5 second passages was useful |
| Passage cap 110 → 180 tokens | ~+2.5–3 s; A/B stopped before it finished (parked) |

## 4. What we did — step by step
1. A/B, 14 questions (8 Hindi, 6 English), fixed seed: "Answer the question itself. Never mention or describe the text above." vs "Answer using the facts in the text above, in your own simple words. Do not mention the text itself."
2. Adopted the second wording.
3. k=2 evaluated on 5 questions (second passage content + real token cost) and rejected.

## 5. What we measured
| Metric | Before | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Groundedness median | 0.179 | 0.266 | 0.40–0.45 | No |
| Key fact present | 9/14 | 10/14 | ↑ | Yes |
| Talks about the text | 0 | 0 | 0 | Yes |

## 6. What worked
Telling a small model what to *do* with the passage, last in the prompt. Higher on 12 of 14 questions.

## 7. What didn't work
**Failure 1 — k=2**: symptom: +58 to +128 prompt tokens per turn; second passages were exercises or duplicates in 4/5. Rejected.
**Failure 2 — reaching 0.40**: cause not identified beyond "the model paraphrases and adds its own example"; the bigger-passage A/B was stopped (it competed with live testing). Parked.

## 8. Error logs
```
A current   n=14 | groundedness median 0.179 mean 0.186 | key fact present 9/14 | talks about the text 0
B use-text  n=14 | groundedness median 0.266 mean 0.253 | key fact present 10/14 | talks about the text 0
```

### 9. Conclusion and next step
- [x] Verdict: adopt the wording; reject k=2; park bigger passages
- [ ] Follow-up experiment: cap 180 + "reuse key terms" on a quiet machine with Hindi books loaded
- [x] Code or docs updated: `tutor.py`
- [ ] Shared with team on:

---

# EXP-009 — Speech output: clip ramp, voice warm-up, retry

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-11 | **Date closed:** 2026-09-11 | **Status:** Worked
**Device tested on:** 8 GB Windows laptop
**Related experiments:** EXP-011 (filler audio)

## 1. Context
Long silences between the first and second audio clip; a first synthesis could take 11.5 s; after
10 idle minutes the page showed "The Hindi voice didn't load" while still speaking.

## 2. Hypothesis
If clips grow gradually and are capped, the voice never waits for a whole long sentence; if the
voice is warmed once per load and failed requests retry once, the first sentence is never lost.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Pre-buffer several clips | Tried earlier: delays the first word by a whole synthesis |
| Filler "Good question" audio | Built, rejected by the user (EXP-011) |

## 4. What we did — step by step
1. Measured rates: model writes Hindi ~12.7 chars/s; Piper synth ≈ 0.02 s + 0.0198 s/char under load; speech ≈ 0.7 s + chars/13.3.
2. Simulated chunking policies on three real Hindi answers; adopted a ramp: clips 18–28, 20–40, 24–52 chars, then 30–64, cutting at sentence end, comma or word.
3. Voice cache keyed on the lowercased language ("Hindi" and "hindi" had been two cache entries); the lobby voice check warms the voice once.
4. `useBackendTts`: one retry after 300 ms on a failed request; the error banner clears on the next success.

## 5. What we measured
| Metric | Before | After (simulated) | Target | Met? |
| --- | --- | --- | --- | --- |
| Silence after first audio (3 answers) | 12.2 / 5.0 / 7.6 s | 1.5 / 1.9 / 1.7 s | < 2 s | Yes |
| Gap clip 1 → clip 2 | 9.6 / 1.4 / 2.8 s | 0.4 / 0.5 / 0.5 s | < 1 s | Yes |
| First audio | unchanged | unchanged | — | — |

## 6. What worked
Writing speed ≈ speaking speed, so gaps only open when the next clip is much longer than the one playing.

## 7. What didn't work
**Failure 1 — idle-connection failure**: first `/api/tts` after 10 idle minutes failed in the browser (every request in the backend log was 200). Cause: most likely a stale keep-alive connection (not proven); fixed by retrying.

## 8. Error logs
```
28 chars  run 1: 11551 ms   (voice cache swap caused by the test's wrong language parameter)
The Hindi voice didn't load, so answers won't be read aloud. Reload the page to retry, or turn the voice off.
```

### 9. Conclusion and next step
- [x] Verdict: adopt
- [ ] Follow-up experiment: measure real gaps from the browser console on a quiet machine
- [x] Code or docs updated: `useTutorSession.ts`, `useBackendTts.ts`, `tts.py`, `routers/tts.py`, `tests/test_tts_warm.py`
- [ ] Shared with team on:

---

# EXP-010 — Library & lobby UI (class / subject / medium, multi-upload)

**Approach:** Electron (desktop shell) + web frontend
**Owner:** surinder-nav | **Date started:** 2026-09-09 | **Date closed:** 2026-09-10 | **Status:** Worked
**Device tested on:** 8 GB Windows laptop
**Related experiments:** EXP-001, EXP-007

## 1. Context
A book uploaded for Class 5 could not be selected (upload offered classes 1–12, the lobby 6–8);
language could change mid-chat; one file at a time.

## 2. Hypothesis
If the lobby's choices come from the library itself and warm up the session before the student
asks, every uploaded book is reachable and the first question is fast.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Static class/subject lists | Drift from what is actually uploaded |

## 4. What we did — step by step
1. `StartPage.tsx` lobby: language / class / subject built from live library coverage; 3-step readiness (STT, TTS, model); hands a primed session to the chat.
2. `SetupPage.tsx`: multi-file upload (sequential), medium (Hindi/English/Marathi) sent with each book.
3. Upload runs as a backend job — leaving the page does not stop it (but keep it open until the last file is *sent*).
4. Scanned PDFs are stopped with an OCR hint (they contain no text).

## 5. What we measured
| Metric | Before | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Upload speed | — | ~6 s per page (594-page book ≈ 60 min) | — | — |

## 6. What worked / 7. What didn't work
Worked as intended. Two uploads failed correctly as scanned PDFs (`Hindi Vyakaran & Rachna.pdf`: 88 characters of text in 216 pages; `Class-X-Hindi Grammar.pdf`: 0 characters on every sampled page of 160) — need OCR first.

## 8. Error logs
```
No text layer found -- this looks like a scanned PDF.
Run it through OCR first (any tool that produces a searchable PDF), then upload the result.
```

### 9. Conclusion and next step
- [x] Verdict: adopt
- [x] Code or docs updated: `App.tsx`, `StartPage.tsx`, `SetupPage.tsx`, `curriculum.ts`, `readiness.ts`, `library.ts`
- [ ] Shared with team on:

---

# EXP-011 — Things we tried that failed or were rejected

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-07 | **Date closed:** 2026-09-11 | **Status:** Failed / Abandoned
**Device tested on:** 8 GB Windows laptop
**Related experiments:** all

## 1. Context
Recorded so these are not retried without a new reason.

## 2. Hypothesis
Each item had its own hypothesis; listed with the result below.

## 3. Why this approach over the alternatives
n/a — this entry is the list of alternatives.

## 4. What we did
| Tried | Result | Why rejected |
| --- | --- | --- |
| Memory/RAM tuning (2026-09-07) | No change | Decode is a CPU wall (~5 tok/s), not a RAM wall |
| `gemma3:1b` | ~2× faster | Incoherent / wrong Hindi and Marathi |
| `qwen2.5:1.5b` (earlier) | Fast English | Cannot produce coherent Hindi/Marathi |
| Navarasa (Indic gemma-2b fine-tune) | Tested | Did not work for this use case (not adopted) |
| `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0` | 44.1 ms/token | Slower than 34.8–39.9 without (dequantisation on CPU) |
| Excerpts accumulated in the system prompt | 27.7 ms/token | Forks the cache (EXP-001) |
| Query-scored passage trimming | Broke an answer | Kept topic sentences, dropped the facts (EXP-001) |
| k=2 passages | +2.9–4.9 s | Second passage rarely useful (EXP-008) |
| Rules in persona with no reminder | 118–159-word answers | EXP-003 |
| "Good question / अच्छा सवाल है" filler audio | Built | User rejected it — reduce real latency instead |
| Chrome's built-in offline Hindi speech recognition | Did not work on this Windows 10 box | App uses IndicConformer on the backend instead |
| Background A/B tests while the user tests | 43–56 s turns | Never run heavy jobs during testing |

## 5–8. Measurements and logs
Kept in the linked experiments above.

### 9. Conclusion and next step
- [x] Verdict: reject (all rows)
- [ ] Shared with team on:

---

# EXP-012 — Clean-up: stale code, libraries and files removed

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-11 | **Date closed:** 2026-09-11 | **Status:** Worked
**Device tested on:** 8 GB Windows laptop
**Related experiments:** EXP-005, EXP-009

## 1. Context
Two days of changes left replaced libraries, dead helpers, stale setup steps and 139 MB of unused files.

## 2. Hypothesis
Removing them changes no behaviour: all 154 tests and the frontend type-check stay green.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Keep pypdf as a fallback | Replaced by PyMuPDF; user asked for exchanged libraries to be removed |

## 4. What we did
| Removed / changed | Why |
| --- | --- |
| `pypdf` (requirements, fallback code, venv) | Replaced by PyMuPDF (EXP-005) |
| `apps/frontend/public/models` (121 MB) + `public/piper-wasm` (18 MB) | Browser TTS removed in `f9f16ad`; nothing referenced them |
| `setup.ps1` / `setup.sh` steps 1b, 5, 7 (browser Piper) | Replaced by one step that runs `scripts/package_tts_voices.py` for the backend voices — setup previously never installed them |
| `apps/frontend/.gitignore` react-sts / ort / piper entries | Files no longer exist |
| `retrieval._terms`, `_TERM_RE`; `query._CHARS_PER_TOKEN_OTHER`; `schemas.ErrorResponse` | Never referenced |
| `docs/MODELS-TRIED.md`, `docs/TTS-8GB-OPTIMIZATION-PLAN.md` | Superseded by this log |
| `scripts/ab_prefill.py`, `scripts/benchmark_models.py` | Measurement tools, not part of the app |
| Ollama models `qwen2.5:1.5b`, `gemma3:1b`, `navarasa-2b`, Indic-gemma Navarasa, `nomic-embed-text`, `paraphrase-multilingual` (~5.8 GB) | Rejected or replaced; only `gemma2:2b` + `bge-m3` are used |
| "Good question" acknowledgement code | Rejected feature, fully reverted |
| Stale comments (sessions, trim_passage, ingest, tutor) and the metrics label "prompt tokens read" | Described old behaviour; prompt tokens include cached ones |
| README | Said answers are spoken in the browser; now documents backend TTS and `ollama pull bge-m3` |
| Added `apps/backend/requirements-dev.txt` | pytest + pytest-asyncio — without them 9 async tests fail |

## 5. What we measured
| Metric | Before | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Backend tests | 154 passed | 154 passed | all | Yes |
| Frontend type-check | clean | clean | clean | Yes |
| Frontend `public/` size | ~139 MB | ~20 KB | small | Yes |

## 8. Error logs
```
9 failed, 68 passed ... PytestUnknownMarkWarning: Unknown pytest.mark.asyncio   (before pytest-asyncio was installed)
```

### 9. Conclusion and next step
- [x] Verdict: done
- [x] Docs kept as-is by decision (`docs/SPEECH-ARCHITECTURE.md`, `docs/RAG-MULTILANG-PLAN.md`)
- [ ] Shared with team on:

---

# EXP-013 — First question after a cold start: warm the embedding model

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-14 | **Date closed:** open | **Status:** Running
**Device tested on:** 8 GB Windows laptop (dev machine, i7-6600U)
**Related experiments:** EXP-001, EXP-002

## 1. Context
First question after starting the app following a two-day gap: **18.0 s to the first token**, 37.0 s
of server time, 61.9 s until the answer finished being spoken. The timing panel put **11.2 s of it
in retrieval**, and the backend log named the part that mattered: `embed 10774`.

Startup already warms the LLM, the recognizer and the voice. It has never warmed **bge-m3**, and the
lobby warm-up cannot: that call deliberately skips retrieval, because searching for the literal
phrase "warm up" pulls noise passages and leaves a prefix no real question matches (measured
2026-09-09: such a warm-up cost 50 s and helped nothing). So the embedding model's 1.2 GB was always
loaded by the student's first question.

## 2. Hypothesis
If the backend embeds one throwaway string during its startup warm-up chain, the first real question
pays no model load, retrieval drops from ~11 s to well under 1 s, and first-token time falls from
18 s to roughly 6–8 s.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Have the lobby warm-up retrieve as well | Its message is the string "warm up"; the passages are noise and the cached prefix is useless to a real question (measured 2026-09-09, 50 s) |
| A separate preload script run at boot | Another moving part, and it would miss every backend restart |
| Accept the cold first question | It is the first impression in every demo, and a demo rarely reaches question two |
| Unload bge-m3 between questions instead | Already measured worse: keep_alive 0 cost +7.5 s per turn, 30 s pushed turns to 80 s |

## 4. What we did — step by step
1. Read the warm-up chain in `app/main.py`: `_warm_model()` → `_warm_stt()` → `_warm_tts()`, run in
   sequence rather than in parallel (started together they starve the one the UI waits on).
2. Added `_warm_embeddings()`: `await embed_query("warm up", model=...)`, using the **store's**
   embedding model rather than config's, because after a re-embed cutover the two differ and warming
   the wrong one leaves the real one cold.
3. Placed it **last** in the chain: the lobby's readiness lights wait on the other three, and nothing
   needs the embedder until the student has actually asked something.
4. Best-effort by design — `OllamaError` and any other exception are logged, never raised. A failure
   costs a slow first question, not a broken server. Skipped entirely when `RAG_ENABLED=false`.

**Environment**
- gemma2:2b + bge-m3 on Ollama 0.34.0, `OLLAMA_KEEP_ALIVE=-1`, `RAG_EMBED_QUERY_KEEP_ALIVE=-1`
- Baseline: the same first-question-after-restart path without the new step

## 5. What we measured
| Metric | Baseline | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Retrieval, first question after a restart | 11.2 s (embed 10,774 ms) | not yet measured | < 1 s | pending |
| First token, first question after a restart | 18.0 s | not yet measured | 6–8 s | pending |
| First token, later questions (unchanged by this) | 4.3–7.1 s | — | — | — |
| Peak RAM | not measured | not measured | — | — |

Baseline is a single live turn (2026-09-14 09:31), not an average. **The backend has not been
restarted yet** — the user was testing, and restarting would have interrupted them — so the "after"
column is genuinely unmeasured rather than assumed.

## 6. What worked
Nothing is proven yet. The mechanism is the same one behind every other warm-up here: a model load
is a fixed cost, and the only question is whether the student or the boot sequence pays it.

## 7. What didn't work
Nothing yet.

**Open risk** — bge-m3 (1.2 GB) now loads at boot alongside gemma2:2b (1.6 GB) on an 8 GB box.
Both were already resident during a lesson, so this moves the load earlier rather than adding a new
one, but the first-question RAM figures have never been measured and should be.

## 8. Error logs
```
2026-09-14 09:31:58 app.routers.chat: turn 36997ms | retrieval 11211ms (embed 10774 dense 338 lex 68)
  -> 1 passages / 70 ctx tokens | ttft 17998ms | prefill 6176ms (627 tok) decode 19030ms (103 tok, 5.4 tok/s)
  | hi best 0.318 headroom +0.182 grounded 0.12
2026-09-14 09:28:38 ai-tutor: Warmed 'gemma2:2b' in 41889ms (keep_alive=-1, num_ctx=4096)
2026-09-14 09:28:52 ai-tutor: STT warm-up done in 14.1s.
2026-09-14 09:29:05 ai-tutor: TTS warm-up done in 13.4s.
   (no embedding warm-up line exists before this change)
```

### 9. Conclusion and next step
Cause identified and fixed in code; the claim is unverified until the backend restarts. Measure the
first question after a clean restart before calling this adopted.
- [ ] Verdict: pending measurement (expected: adopt)
- [ ] Follow-up experiment: first turn after a restart, and peak RAM with both models resident
- [x] Code or docs updated: `app/main.py`
- [ ] Shared with team on:

---

# EXP-014 — Hindi transcripts came back with every word doubled

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-14 | **Date closed:** open | **Status:** Running
**Device tested on:** 8 GB Windows laptop (dev machine)
**Related experiments:** EXP-003 (Shyam, English STT), EXP-015

## 1. Context
Offline Hindi speech-to-text, which had been usable, started returning text like:

```
काली काली मृ मृदा कहाँ कहाँ पााय जा जाती है है
कालाली दिन बिन विधता का कहा वँ पढ़ाई जाई जाती है
```

for "काली मृदा कहाँ पाई जाती है". Words repeat and vowels stretch. The garbled question then reached the
tutor, which answered from it (groundedness 0.12, and the answer placed black soil in the hills).

## 2. Hypothesis
Word-level doubling and stretched vowels are what a CTC recogniser emits when the audio it receives
contains the speaker twice or is time-distorted. If each recording is isolated and the resampler is
correct in both directions, the doubling disappears without touching the model.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Blame the model or the speaker | It had worked on the same laptop and voice; a model does not regress on its own |
| Swap the IndicConformer export | int8 is measurably worse (Hindi WER ~16% → ~30%), and nothing pointed at the model |
| De-duplicate repeated words in the transcript | Hides the fault and would corrupt genuinely repeated words ("धीरे-धीरे") |
| Ask the user to re-record until it works | Not a fix, and it moves a code bug onto the person demoing |

## 4. What we did — step by step
1. Confirmed from `backend.err.log` that the turn itself was healthy (`hi best 0.318`, one passage
   retrieved) — so the fault was the audio reaching `/api/stt`, not retrieval or the LLM.
2. Listed the machine's active audio endpoints: `Get-PnpDevice -Class AudioEndpoint -Status OK`
   returned only the Realtek microphone array and Realtek speakers. **No Bluetooth device**, which
   makes the low-rate-mic path unlikely to be this user's cause.
3. Read `hooks/stt/useIndicSpeechToText.ts` and found three defects:
   - **Shared buffer.** `node.onaudioprocess` pushed into `chunksRef.current`. A recorder that
     survived a previous utterance keeps firing into whatever that ref points at — by then the NEW
     recording's array — so the model receives the speaker twice, interleaved. This matches the
     symptom exactly.
   - **Guard on state, not a ref.** `if (!ready || isListening) return;` — `setIsListening` is
     asynchronous, so two taps in one tick both saw `false` and opened two microphones.
   - **Broken upsampling.** `downsample()` averaged the input window each output sample covered.
     Below 16 kHz (a Bluetooth headset in call mode is 8 kHz) that window is empty, so it wrote a
     zero between every real sample: a buzzing, aliased copy of the speech.
4. Fixes: each recording captures its own `chunks` array; `startingRef` guards the open; any surviving
   recorder is torn down before a new one starts; `resampleTo16k()` averages downwards and
   interpolates upwards; `getUserMedia` now asks for mono at 16 kHz with echo cancellation, noise
   suppression and auto gain.
5. Added diagnostics, because a bad transcript looked identical whatever the cause:
   `[stt] mic "<device>" | track <n> Hz | AudioContext <n> Hz -> 16000 Hz (no resampling|downsampling|UPSAMPLING)`
   and loudness on the round-trip line: `(3.2s clip, rms 0.041, peak 0.83 -> 28 chars)`.
6. `npx tsc --noEmit` clean.

**Environment**
- Frontend: React + Vite dev server; Chrome `--app` window, profile "AI Tutor POC"
- Backend: sherpa-onnx 1.13.6, IndicConformer-600M CTC fp32, `STT_NUM_THREADS=4`
- Hardware: Realtek microphone array (built in), no external audio device

## 5. What we measured
| Metric | Baseline | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Words doubled in a Hindi transcript | 5 of 8 words in the sample | not yet measured | 0 | pending |
| Accuracy / WER | not measured formally | not yet measured | — | pending |
| Transcribe time | 1.2 s | unchanged (expected) | — | — |

## 6. What worked
Unverified. The shared-buffer defect is real and is the only one of the three that explains
*interleaved* duplication; the other two are correctness fixes that this machine may never have hit.

## 7. What didn't work
**Failure 1 — the doubled transcript**
- Symptom: every word repeated, vowels stretched (above).
- What we tried: audio-endpoint check (ruled out a Bluetooth 8 kHz mic), code review of the recorder.
- Root cause: **not confirmed.** Three defects found and fixed, one of which (the shared buffer)
  matches the symptom. Waiting on the user's next recording plus the new console line.
- Parked, not a dead end.

## 8. Error logs
```
(transcripts, from the app UI)
कालाली दिन बिन विधता का कहा वँ पढ़ाई जाई जाती है
काली काली मृ मृदा कहाँ कहाँ पााय जा जाती है है

(the turn that answered it was otherwise healthy)
turn 36997ms | ... | hi best 0.318 headroom +0.182 grounded 0.12

(audio endpoints, PowerShell)
Microphone Array (Realtek Audio)
Speakers / Headphones (Realtek Audio)
```

### 9. Conclusion and next step
Three defects fixed; the causal one is not yet proven. The diagnostics added here are the point:
the next bad transcript will say whether the audio or the model is at fault.
- [ ] Verdict: pending confirmation
- [ ] Follow-up experiment: one recording with the console open; if doubling persists with
      `(no resampling)` and healthy rms, the fault is the model or the microphone, not the pipeline
- [x] Code or docs updated: `hooks/stt/useIndicSpeechToText.ts`
- [ ] Shared with team on:

---

# EXP-015 — Answers inaudible while the backend synthesised every clip

**Approach:** Multilingual
**Owner:** surinder-nav | **Date started:** 2026-09-14 | **Date closed:** open | **Status:** Running
**Device tested on:** 8 GB Windows laptop (dev machine)
**Related experiments:** EXP-009, EXP-014

## 1. Context
The user could not hear answers, while the app showed "Voice on" and reported the answer as spoken.
The backend disagreed: `backend.out.log` held a long run of `POST /api/tts?language=Hindi 200 OK`,
and the Hindi voice had loaded (`hindi TTS voice ready (22050 Hz)`). Audio was being produced and
not heard.

## 2. Hypothesis
Playback is failing in the browser and the failure is being discarded. `playQueue()` ended with
`audio.play().catch(done)` — `done` is the same handler used for a clip that finished normally, so a
refused clip is indistinguishable from a played one, and the loop moves on silently. If the rejection
is reported instead, it will name which of the three real causes this is.

## 3. Why this approach over the alternatives
| Option considered | Why not chosen |
| --- | --- |
| Unlock audio on every button, assuming it is the autoplay policy | A guess dressed as a fix; if the cause is a muted output it changes nothing and hides the evidence |
| Assume the OS volume or output device | Cannot be verified from here, and the endpoint list showed only the built-in speakers |
| Switch playback back to Web Audio | A large change to the audio path, justified only once the cause is known |

## 4. What we did — step by step
1. Confirmed from `backend.out.log` that every clip synthesised (`200 OK`), so the fault is downstream
   of the backend.
2. Confirmed the machine has one output: `Speakers / Headphones (Realtek Audio)`.
3. Patched `hooks/tts/useBackendTts.ts`:
   - `audio.play().catch(...)` now logs `[tts] playback failed (<ErrorName>): <message>` and raises a
     user-visible banner, with a distinct message for `NotAllowedError` (the browser's autoplay
     policy) versus anything else (output device / decode).
   - Added `audio.onplaying = () => console.log("[tts] clip playing")` — positive proof that sound
     actually started, rather than a clip that was created, dropped and counted as spoken.
   - `onplaying` is cleared in `done()` and in `stop()` alongside the other handlers.
4. `npx tsc --noEmit` clean.

**Environment**
- Backend TTS: sherpa-onnx + Piper `hi_IN-priyamvada-medium`, `TTS_SPEED=0.9`, `TTS_NUM_THREADS=2`
- Frontend: HTMLAudioElement playback of WAV blobs, one clip at a time
- Output: Realtek speakers (only active endpoint)

## 5. What we measured
| Metric | Baseline | After | Target | Met? |
| --- | --- | --- | --- | --- |
| Clips synthesised by the backend | all (200 OK) | unchanged | — | — |
| Clips actually heard | 0 | not yet measured | all | pending |
| Diagnosis available when it fails | none | error name + banner | a named cause | yes (by construction) |

## 6. What worked
Not yet established. What is established is that the previous code could not have told us: a swallowed
rejection and a finished clip took the same path.

## 7. What didn't work
**Failure 1 — no audible answer**
- Symptom: silence; backend returns 200 for every clip; the UI reports the answer as spoken.
- What we tried: backend log check, audio endpoint enumeration, code review of the playback loop.
- Root cause: **not identified.** Three candidates remain: the browser's autoplay policy
  (`NotAllowedError`), a muted or incorrect Windows output for that window, or a clip the browser
  cannot decode. The next run separates them.
- Parked, not a dead end.

**Failure 2 — a design fault this exposed**
- An optimisation path (`.catch(done)`) treated an error as a normal completion. Silent fallbacks
  produce exactly this: a feature that is broken and reports success.

## 8. Error logs
```
(backend, every clip succeeded)
INFO: 127.0.0.1:55585 - "POST /api/tts?language=Hindi HTTP/1.1" 200 OK    (x6, one per clip)
2026-09-14 10:01:11 app.services.tts: hindi TTS voice ready (22050 Hz)

(audio endpoints, PowerShell)
Speakers / Headphones (Realtek Audio)

(what the browser console will now print, one of:)
[tts] clip playing
[tts] playback failed (NotAllowedError): play() failed because the user didn't interact with the document first
```

### 9. Conclusion and next step
The silence is on the browser side and was being hidden by the code. Reporting comes first; the fix
follows the name the next failure gives us.
- [ ] Verdict: pending diagnosis
- [ ] Follow-up experiment: one question with the console open; `NotAllowedError` → unlock audio on
      Send as well as on the mic tap; `clip playing` with silence → Windows volume mixer / output device
- [x] Code or docs updated: `hooks/tts/useBackendTts.ts`
- [ ] Shared with team on:

---

## Files changed since `f9f16ad`

**Backend (modified):** `app/config.py`, `app/main.py`, `app/routers/chat.py`, `app/routers/library.py`,
`app/routers/tts.py`, `app/schemas.py`, `app/services/ollama_client.py`, `app/services/sessions.py`,
`app/services/tts.py`, `app/services/tutor.py`, `app/services/rag/chunking.py`, `embeddings.py`,
`ingest.py`, `pdf_text.py`, `query.py`, `retrieval.py`, `store.py`, `requirements.txt`, `tests/test_retrieval.py`
**Backend (new):** `app/services/rag/legacy_hindi.py`, `requirements-dev.txt`, tests `test_exercise_order.py`,
`test_followup.py`, `test_legacy_hindi.py`, `test_reprime.py`, `test_tts_warm.py`, `test_turn_rules.py`
**Frontend (modified):** `App.tsx`, `components/ChatBubble.tsx`, `MicButton.tsx`, `TurnMetricsPanel.tsx`,
`hooks/tts/useBackendTts.ts`, `useTutorTts.ts`, `hooks/stt/useIndicSpeechToText.ts`,
`hooks/useTutorSession.ts`, `index.css`,
`pages/SetupPage.tsx`, `TutorPage.tsx`, `services/api.ts`, `library.ts`, `types/index.ts`, `.gitignore`
**Frontend (new):** `config/curriculum.ts`, `pages/StartPage.tsx`, `services/readiness.ts`
**Scripts / docs:** `scripts/setup.ps1`, `setup.sh`, `start.ps1` (Ollama priority AboveNormal),
`README.md`, `docs/AI-TUTOR-SYSTEM-GUIDE.md`, this file. (`scripts/ab_prefill.py` and `scripts/benchmark_models.py` were used for
the measurements, then removed.)

**New settings (all in `app/config.py`, overridable in `.env`):** `OLLAMA_REPRIME_AFTER_REPLY=true`,
`TUTOR_RULES_IN_PERSONA=true`, `RAG_FOLLOWUP_REUSE=true`, `RAG_DEDUP_CONTEXT=true`,
`RAG_CEILING_HI=0.50`. Set any of the first three to `false` to switch that change off.
