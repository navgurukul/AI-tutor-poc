# Multilingual RAG — Development Plan

Execution plan derived from `docs/RAG_ architecture.pdf` ("Grounding the Tutor",
engineering decision record, revised after architecture review).

Target: **a Hindi-speaking Class 9 student asks in Hindi, the tutor answers from
the English textbook the school owns, and cites chapter and page — offline.**

Everything below is written against the code as it actually stands on
`aibharat-stt` (HEAD `398cd48`) and `feature/latency-optimization-rag`
(HEAD `f0e2b44`), merge-base `650ee47`.

---

## 0. Pre-flight — verified on this machine

| Claim in the doc | Status |
|---|---|
| `bge-m3` pulled in Ollama | ✅ `bge-m3:latest`, 1.2 GB |
| Fallbacks available | ✅ `granite-embedding:278m`, `embeddinggemma:latest` |
| Generators available | ✅ `gemma2:2b`, `gemma3:4b`, `qwen2.5:1.5b` |
| sqlite-vec loadable | ✅ `sqlite_vec` in `apps/backend/.venv` (Python 3.12) |
| SQLite 3.53.1 | ✅ |
| FTS5 `trigram` survives Devanagari | ✅ verified: `MATCH '"कार्य"'` returns the row |

Nothing is blocked on a download or an environment fix.

### Corrections to the doc's own assumptions

**P0-a — the phase 00 merge is _not_ "additive only".** The doc says conflicts
"should be additive only". They will not be. Both branches modify the same 13
files:

```
apps/backend/app/config.py            apps/frontend/src/App.tsx
apps/backend/app/main.py              apps/frontend/src/hooks/useTutorSession.ts  (275 lines on stt)
apps/backend/app/routers/chat.py      apps/frontend/src/pages/TutorPage.tsx
apps/backend/app/schemas.py           apps/frontend/src/services/api.ts
apps/backend/app/services/tutor.py    apps/frontend/src/index.css
apps/backend/app/services/ollama_client.py
apps/backend/requirements.txt         apps/backend/.env.example
```

`useTutorSession.ts` and `TutorPage.tsx` are the two that need real attention —
the STT branch rewrote both around the speech hooks, the RAG branch added
citation rendering and the setup page. Budget the merge as a task, not a step.

**P0-b — `num_ctx` conflicts in the wrong direction.** RAG branch has `4096`,
`aibharat-stt` lowered it to `3072` for CPU latency. Naive conflict resolution
takes one of the two; phase 04 needs it to go **up**. Resolve deliberately.

**P0-c — the session already knows the language.** `TutorProfile.language`
(`apps/backend/app/schemas.py:47`) already carries `"English"` / `"Hindi"` /
`"Marathi"`, set from `apps/frontend/src/config/languages.ts`. Closed·03 does
not need new plumbing end-to-end — it needs a **name → code** mapping and a
gate that reads it. That is a smaller job than the doc implies.

**P0-d — three of the seven "non-blocking findings" the doc defers are real
bugs and are folded into the phases below**, because they land in code we are
already touching:

- FTS5 external-content **delete ordering** (phase 01) — for
  `content='chunks'` tables the index delete must be issued *before* the
  content row is gone, or the terms cannot be found to remove and stale rows
  keep matching.
- The **lexical leg has no grade filter** (phase 04) — FTS5 has no partition
  key. Without an explicit join a Class 6 student gets Class 9 passages fed
  into RRF.
- The **40-character chunk floor** (phase 03) — applied after breadcrumb-free
  text, it silently drops short definitions, which is exactly the content a
  definition question wants.

**P0-e — existing local `data/library.db` must be discarded.**
`_check_or_stamp_meta()` (`store.py`) refuses to open a store stamped with a
different model or schema version. That is correct behaviour and we want it;
it means the dev DB is rebuilt at phase 02, not migrated.

---

## Phase 00 — Branch

```
git checkout aibharat-stt
git checkout -b feature/multilang-rag
git merge feature/latency-optimization-rag
```

`feature/latency-optimization-rag` stays untouched as the English-only
reference. Merge only writes to the target.

**Resolution rules for the conflicts:** backend `config.py` — union both
setting blocks, `num_ctx` deferred to phase 04. `chat.py` — keep the STT
branch's temperature/language logic, add the RAG branch's `_retrieve_context`
call. `tutor.py` — keep the STT branch's script-discipline prompt, add the
context block. Frontend — take the STT branch's `useTutorSession.ts` wholesale
and re-apply the RAG branch's citation plumbing on top.

**Done when:** backend starts, `/health` responds, an English question still
answers, and STT/TTS still work for Hindi.

**Files:** `config.py`, `requirements.txt`, `app/main.py`, and the 13 above.

---

## Phase 01 — Store: language column + FTS5

`services/rag/store.py`

1. `SCHEMA_VERSION = 3`.
2. `language` column on `documents`; `language` as a **vec0 metadata column**,
   *not* a second partition key — grade × language × subject fragments the
   partitions below useful size.
3. Model-scoped vector table: `chunk_vectors_bge_m3`, with the active table
   name recorded in `meta`. One line now; a device-wide schema migration if
   retrofitted later (Closed·05).
4. FTS5:

```sql
create virtual table chunks_fts using fts5(
    text, content='chunks', content_rowid='id', tokenize='trigram');
```

5. Write FTS rows **inside the same transaction** as `add_chunks()`.
6. Extend `delete_document()` — it already deletes vectors by hand because vec0
   ignores foreign keys; FTS5 external-content tables need the same care, and
   the delete command must be issued **before** the `chunks` rows go (P0-d).

**Done when:** a unit test ingests two chunks, deletes the document, and
asserts `chunks`, `chunk_vectors_bge_m3` **and** `chunks_fts` are all empty.

---

## Phase 02 — Swap the embedding model + write the re-embed job

`services/rag/embeddings.py` · `config.py` · `services/rag/ingest.py`

1. `rag_embedding_model: "bge-m3"`, `rag_embedding_dims: 1024`.
2. bge-m3 needs no task prefix — **leave `_needs_prefix()` in place** so the
   nomic path stays correct if anyone switches back.
3. Write the **re-embed job now, while the schema is still moving**: read
   `chunks.text`, fill a second model-scoped vec0 table in the background using
   the progress-polling machinery `ingest.py` already has (`IngestJob`,
   `IngestionService.start/_run`), repoint `meta` on completion, drop the old
   table. Same job the student-upload path runs, pointed at content already in
   the file.

Rationale: this is what makes the embedding choice reversible rather than a
one-way door (Closed·05). `embeddinggemma` stops having an expiry date.

**Done when:** an ingest produces 1024-dim vectors, `meta` stamps
`bge-m3`/`1024`/`chunk_vectors_bge_m3`, and the re-embed job runs to cutover on
a populated library while search keeps answering.

---

## Phase 03 — Chunk bounds and heading detection

`services/rag/chunking.py` · `services/rag/pdf_text.py`

1. Split `rag_chunk_chars` into **target 1200 / max 2000 / min 40**. Paragraph
   packing uses `target`; `_split_long_paragraph()` uses `max`; the trailing
   `>= 40` filter becomes `min`. The gap lets a section run slightly long to
   stay whole rather than being cut at character 1,201.
2. Fix two defects in `looks_like_heading()`
   (`pdf_text.py:134`):
   - the title-case branch (`capitalised >= max(2, len(words)*0.7)`) makes
     **any two capitalised words** a heading — figure labels like "Xylem
     Vessels" become spurious hard cuts;
   - **Devanagari has no case**, so `all(c.isupper())` and the capitalised
     count can never fire — only `_NUMBERED_HEADING` can ever match for Hindi
     and Marathi books. Add script-aware detection (short line, no sentence
     end, followed by a paragraph — plus the numbered form).
3. Re-check the 40-char floor against short definitions (P0-d).

**These bounds govern splitting only.** They are characters because splitting
is a text operation. They must not be mistaken for a context budget: 2,000
characters of English is ~500 tokens; 2,000 characters of Hindi can be three
times that. That is phase 04's problem.

**Done when:** chunking an English and a Devanagari PDF produces sane heading
counts in both, and no chunk exceeds `max`.

---

## Phase 04 — Hybrid retrieval + RRF + token budget

`services/rag/retrieval.py` · `services/ollama_client.py` · `config.py`

1. Dense and BM25 over the **same grade partition**, 50 candidates each, fused
   with **RRF at k=60**. The lexical leg needs an explicit
   `join chunks → documents where documents.grade = ?` — FTS5 has no partition
   key (P0-d).
2. **Delete the subject-filter retry** (`retrieval.py`, the `if not hits and
   subject:` block). Subject leaves the query entirely — it is already inside
   every vector via `Chunk.embedding_text()`'s breadcrumb.
3. `k_context` stays 4. `retrieve()` stays **non-raising**.
4. **Build the MATCH string; never pass the question through** (Closed·02).
   Strip punctuation → drop stopwords and tokens under 3 characters → double
   any embedded `"` → quote each surviving term → join with `OR` → append the
   full question as one quoted phrase for exact substring matching under
   trigram.

   Measured, and the reason this matters:
   ```
   MATCH 'What is a tissue'     → []
   MATCH 'Explain tissue'       → []
   MATCH 'tissue'               → 3 hits
   ```
   **A unit test must assert a natural-language question returns > 0 rows**, or
   this regresses the first time someone simplifies the builder.
5. Assemble the context block against a **token budget**, not `k_context`
   alone (Closed·04). Passages are added **whole** until the budget is reached;
   `k` falls from 4 toward 2 rather than a passage being cut — three whole
   passages beat four half ones. Count with the model's own tokenizer where
   reachable, otherwise a per-script characters-per-token constant that **errs
   low**.
6. Raise `num_ctx` to fit the worst Devanagari case (resolving P0-b), and
   **re-measure RSS with it** — the KV cache scales with the window, so the
   1.6 GB / 3.3 GB figures in the doc do not hold at a larger one.

**Done when:** a natural-language question returns lexical rows; a Class 6
question never surfaces a Class 9 passage; and a 4-passage Devanagari prompt
fits inside `num_ctx` with the system prompt intact.

---

## Phase 05 — Language-aware relevance gate

`services/rag/retrieval.py` · `config.py`

1. **Replace `rag_max_distance`** with two mechanisms:
   - a **relative gate** — keep hits within **+0.12 of the best hit**, which
     normalises away the language offset because every candidate for one query
     shares its query language;
   - a **per-query-language ceiling** that rejects everything when even the
     best hit is too far. Starting values **en 0.45 · hi 0.62 · mr 0.62**, plus
     a bucket for **Latin-script Indic** with its own measured ceiling.

   These are starting points to be measured in phase 06, **not constants**.
2. Apply the gate to the **dense leg, before fusion** — after RRF you are
   ranking by fused position and the distances are gone.
3. **Query language comes from the session** — `TutorProfile.language`, set by
   the ASR selection or the UI toggle (P0-c). Map name → code. Text sniffing is
   a **fallback only**, and when the fallback is unsure it applies the **most
   permissive** ceiling, not the strictest: a false accept costs one noisy
   passage; a false reject costs the entire answer and says nothing.
4. **Wire the abstention rule** (Closed·01): if the dense leg is empty after
   gating, `retrieve()` returns `[]` and **BM25 is never consulted**. If
   something does survive, every passage in the final four must either clear
   the gate itself **or** be an immediate neighbour, in the same document, of
   one that did.

Why 4 matters: BM25 alone can never put a citation in front of a student. An
answer that is wrong is a bad answer; an answer that is wrong *and carries a
citation to the student's own textbook* is a different category of failure.

**Done when:** an out-of-syllabus question in each language returns **zero
chunks**, and a Hindi question against an English book returns the right ones.

---

## Phase 06 — Evaluation harness

`routers/library.py` · `scripts/`

`POST /api/library/search` already runs retrieval without the model — build on
it.

1. A golden set of **30–50 real questions per language**, each with its
   expected chunk.
2. A report of **recall@50, precision@4, MRR, nDCG@4 — split by query
   language**.
3. A **calibration mode** printing on-topic against off-topic distance
   distributions, so the phase 05 ceilings are measured rather than guessed.
4. Two slices matter as much as the ranked ones:
   - **romanized** Hindi and Marathi ("utak kya hai") — the input the ceilings
     are most likely to mishandle, and the half of the problem that was never
     tested;
   - **out-of-syllabus**, expected result **zero chunks** — the only test that
     can tell a working gate from one tuned into permissiveness.

**Done when:** the harness runs from the CLI and prints a per-language table.

---

## Phase 07 — Verification

Run in order. 3, 4, 6 and 10 are the ones that justify the whole project.

1. Ingest one English and one Devanagari textbook. `/health` reports the
   library available; `meta` stamps `bge-m3` / `1024` against the model-scoped
   table.
2. English question → English book. The control.
3. **Hindi question → English book.** *This is the case that fails today and
   the single most important check in this list.*
4. **Same question in romanized Hindi** retrieves the same passages. The check
   that would have caught Closed·03.
5. A **natural-language** question (not a bare keyword) returns > 0 BM25 rows,
   and BM25 alone still retrieves an exact Devanagari term (`कार्य`).
6. **Something the library does not cover, in each language.** The tutor must
   answer unaided and **cite nothing**. A citation here means the gate is not
   doing its job.
7. Count the prompt's tokens at k=4 against a Devanagari book; confirm it fits
   `num_ctx` with the system prompt intact.
8. Run the harness; record recall@50 per language, romanized included. This is
   the baseline every future change is measured against.
9. **Student-add path on the target laptop.** Upload a book, confirm background
   ingestion with progress while the tutor stays answerable, time it end-to-end.
10. **Run the re-embed job on a populated library**; confirm cutover with the
    tutor answering throughout. Untested, the embedding choice is not reversible.
11. Delete a student-added book. Chunks, vectors **and** FTS rows all disappear
    — no stale citation survives.
12. On the **target laptop**: TTFT at k=4 vs k=2 on **Devanagari** passages, and
    total RSS with bge-m3 and the generator both resident at the raised
    `num_ctx`. Also pull `gemma3:1b` — Gemma 3's multilingual training at a
    smaller size may beat gemma2:2b on Devanagari for less RAM.

### Definition of done

A Hindi-speaking Class 9 student asks a question in Hindi, the tutor answers
from the English textbook the school actually owns, and cites the chapter and
page. If that works offline on the target laptop, this is done. If it does not,
nothing else here matters.

---

## Deferred (and what brings each back)

| Deferred | Revisit when |
|---|---|
| HNSW / ANN | Past ~100k chunks **per grade partition** (~100 student books), where flat crosses 100 ms. Brings tombstone compaction with it. |
| `embeddinggemma` over bge-m3 | Whenever on-device ingestion proves intolerable. No longer gated on the ship date — the re-embed job makes it a background migration. Costs 2 questions in 10 at rank 1. |
| Reranking | Once recall@50 is measured and good but precision@1–4 is not. Must save more CPU prefill than it costs. |
| Quantization | Around 1 GB of vectors. We are at 63.6 MB. |
| Subject as a hard filter | Only on a measured precision problem, **and** with upload/session subjects from one controlled vocabulary. |
| `gemma3:4b` as default | Once RAM headroom on the real device is known. Better Devanagari on a 16 GB fleet. |

Non-blocking review findings still unaddressed after this plan: RRF weighting,
phase ordering, corpus size behind the model choice, and the two disagreeing
latency tables in the source document.
