# Groundedness: does the tutor say only what the book it read actually says?

The corpus is `data/PDF English/Class6_Sci_book.pdf` — *General Science, Standard
Six*, Maharashtra State Bureau of Textbook Production and Curriculum Research,
132 pages, ingested into `apps/backend/data/library.db` — 447 chunks before
ingest-time filtering, 327 after (see `RAG_FILTER_CORPUS`).

This directory holds three things:

| file | what it is |
|---|---|
| `README.md` | this document — the method, with a worked example |
| `evalset.json` | the gold set: 13 queries, 31 verbatim book quotes, 12 reference answers, 14 judge-calibration statements |
| `results/` | one Markdown report, one raw transcript and a CSV row per run |

Run it with the backend up:

```bash
python3 scripts/eval/groundedness_eval.py --label v1
python3 scripts/eval/groundedness_eval.py --selftest          # grade the judge only
python3 scripts/eval/groundedness_eval.py --rescore docs/groundedness/results/run-v1-4db01e25.json
```

---

## Why this is separate from `benchmark.py`

`packaging/windows/benchmark.py` already answers **"did the right passage reach
the prompt?"** — it searches for an answer-key phrase and reports where it
ranked and whether the character budget cut it.

This answers the question *after* that one: **given what the model actually
read, is every sentence it wrote supported by that text?**

The two fail independently, which is the whole reason to measure both:

- a turn can retrieve exactly the right page and still invent a sentence;
- a turn that retrieved the wrong page can still be *right*, from the model's
  own memory — an answer that looks perfect while the retrieval pipeline
  contributed nothing.

The second case is invisible to a retrieval metric and invisible to a human
spot-check. It is the one this document exists to make countable.

---

## What is measured

Everything is measured against **the excerpt block the model actually read**,
obtained by setting `return_context: true` on the chat request — never against
the citations. `within_budget()` routinely drops the second retrieved passage
before the prompt while the UI still lists it as a source, so grading against
citations grades an answer against pages the model never saw.

| metric | definition |
|---|---|
| **Groundedness** | supported claims ÷ scorable claims |
| **Contradictions** | claims the excerpt (or the book) makes false — reported separately, never averaged in |
| **Key coverage** | how much of what the book answers with the reply actually says |
| **Context recall** | how many gold quotes reached the prompt at all |
| **Abstention** | on an off-syllabus query, that no textbook page was cited |

Groundedness is reported two ways. **Micro** pools every claim, so a long answer
weighs more than a short one. **Macro** averages the per-turn scores, so every
turn weighs the same. They are printed side by side because they answer
different questions and neither is the honest one on its own.

### Why key coverage sits next to it

Groundedness alone is trivially gamed: a tutor that answers "Friction is a
force." scores 100%. Key coverage is the counterweight — the phrases the book
itself answers with, authored from the page before any model was run. The pair
is what sorts a turn into one of four outcomes:

| | **key covered** | **key missing** |
|---|---|---|
| **grounded** | grounded and complete | grounded but thin — retrieval found a related page, not the answer |
| **ungrounded** | right, but not from the book — the RAG pipeline contributed nothing | ungrounded and incomplete |

"Right, but not from the book" is the interesting cell. Those turns look fine
in the UI and tell you nothing works.

### What counts as a claim

A claim is a sentence, minus the sentences that assert nothing:

- questions ("Why do you think the magnet settles that way?")
- the second-person invitation the socratic style rule *requires* at the end of
  every reply ("Watch the trees along the roadside at different times of day")
- stray headings the model emitted despite being told not to

Counting those as unsupported would put a floor under every score as a penalty
for following the prompt. They are excluded, counted, and printed in the report
so the exclusion can be audited.

Claims stay at sentence granularity on purpose. Splitting further into atomic
propositions needs a model, and a model that splits is a model that can quietly
drop half a sentence before anything has been judged. The cost of that choice
is real and shows up in the results: a compound sentence that is half right
("There are two main types of joints: fibrous and cartilaginous") gets one
verdict, and the judge tends to award it to the half that is supported.

---

## Worked example

This is the whole calculation on one turn, taken verbatim from the `v1` run.

### The query

```
What are the types of joints in our body?
```

### What the book says (`evalset.json`, item `A9-joints`, PDF p.71)

> Joints : Joints are the places where two or more than two bones are connected
> to each other. Joints are of two types.

> **Movable Joint** — Bones can move. Examples : bones of arms and legs

> **Immovable Joint** — Bones cannot move. Example : bones of the skull. (Other
> than the lower jaw)

Every quote in the gold set is byte-for-byte what `library.db` holds — the
harness refuses to run if any of them has stopped matching, so "the model read
the answer" is decided by string containment and never by a human deciding that
two pages are about the same thing.

### What the model actually read

Two passages, 403 characters. Only **1 of the 4** gold quotes was among them:
the definition of a joint arrived, the two type names did not. Both are
figure-caption fragments under 80 characters, and the retriever ranked an
exercise page above them.

### The response

> Joints are the places where two or more than two bones are connected to each
> other. There are two main types of joints: fibrous joints and cartilaginous
> joints. Fibrous joints allow for slight movement, while cartilaginous joints
> allow for more flexible movement. Examples of fibrous joints include the
> sternoclavicular joint and the costovertebral joint, while examples of
> cartilaginous joints include the shoulder and hip joints.

### The scoring

| # | claim | verdict | why |
|---|---|---|---|
| 1 | Joints are the places where two or more than two bones are connected to each other. | supported | verbatim in the excerpt |
| 2 | There are two main types of joints: fibrous joints and cartilaginous joints. | supported | the judge matched "Joints are of two types" — **and awarded the sentence to the half that was supported.** The type names are invented; the book says movable and immovable |
| 3 | Fibrous joints allow for slight movement, while cartilaginous joints allow for more flexible movement. | **unsupported** | nothing in the excerpt says this |
| 4 | Examples of fibrous joints include the sternoclavicular joint... | **unsupported** | nothing in the excerpt says this |

```
groundedness  = supported / scorable   = 2 / 4 = 0.50
key coverage  = facts present / facts  = 2 / 2 = 1.00
context recall= gold quotes read / all = 1 / 4 = 0.25
outcome       = ungrounded + key covered -> "right, but not from the book"
```

Read across the row, the turn diagnoses itself. The definition was grounded
because it was retrieved. Everything after it is Class 11 anatomy the model
recalled on its own, because the two sentences that would have said *movable*
and *immovable* were never put in front of it. **The fix is in chunking, not in
the prompt** — and no amount of prompt work would have found that, because the
answer reads perfectly well.

Claim #2 is also the honest limit of sentence-level scoring, printed here rather
than hidden: it is half true and scored whole.

---

## The judge

Support is decided by a local LLM judge — `gemma3:4b` through the same Ollama
the tutor uses, deliberately larger than the `qwen2.5:1.5b` being graded so it
is not marking its own homework. A word-overlap score cannot tell *"like poles
repel"* from *"like poles attract"* — they are built from identical words — and
those are exactly the errors worth finding.

`--lexical` runs a word-overlap scorer instead, for a machine with no Ollama. It
is a floor, not a second opinion: on the same `v1` transcript it scored 29%
against the judge's 71%, because the tutor paraphrases and overlap punishes
paraphrase. Use it to spot a turn that shares almost no vocabulary with what it
read; do not compare its number to a judged one.

Each claim is put as **two binary questions**, not one three-way verdict:

1. *Does the excerpt state this, or does it follow directly?* → **supported**
2. if not — *Does the excerpt say something that makes this false?* →
   **contradicted**, else **unsupported**

A second call is only paid when the first says no.

This shape was measured, not assumed. Asked for a three-way verdict in one shot,
gemma3:4b wrote a correct paraphrase of the excerpt and then chose the wrong
label:

| judge design | calibration | missed real support | waved a false claim through |
|---|---|---|---|
| one three-way verdict | 12/14 | 17% | 12% |
| same, leaning harder on polarity | 10/14 | 33% | 0% |
| **two binary questions** | **11/14** | **0%** | **12%** |
| two binary questions + worked examples | 11/14 | 0% | 12% (and lost the magnet trap) |

The two-question form never misses real support, and its remaining errors land
on the harmless side — calling a polarity flip *unsupported* rather than waving
it through as *supported*.

### The judge is graded before the tutor is

`evalset.json` carries 14 statements whose verdict is already known: true
paraphrases, polarity flips ("Like poles of two magnets attract each other"),
and plausible-but-absent facts ("Sound travels through air at about 330 metres
per second"). Every run scores these first and prints the result above the
results:

```
JUDGE CALIBRATION  11/14 known verdicts correct (79%)
  missed real support 0%   waved a false claim through 12%
```

Those are the error bars on every number in the run. A groundedness score is
worth exactly what its judge is worth, and publishing one without this is
publishing a number nobody can size.

### Two things the judge does not decide alone

**Known errors override it.** Each item carries hand-written patterns for the
specific ways this question goes wrong — `like poles attract`, `a lever has two
parts`, `jupiter ... is an inner planet`. A match is a contradiction whatever
the judge thought. These mean *contradicts the textbook*, which is a stronger
and more useful notion than *contradicted by the excerpt this turn happened to
read*: a student is harmed by a false statement regardless of what was
retrieved. The calibration above deliberately does **not** use these patterns,
so the printed error rate stays an estimate of the judge alone rather than of
the judge plus its answer sheet.

**Its quotes are checked.** The judge is told to copy the supporting sentence
word for word, so the harness verifies that sentence is really in the excerpt.
It is worth verifying: over the first full run, 2 of 28 supported verdicts
rested on a line that had never been in front of it — once it echoed the claim
back as its own evidence, once it recalled a sentence of the textbook from
elsewhere. These are flagged in the report with ⚠ and counted in the summary.
They are **not** auto-downgraded: the verdict can be right while the quote is
sloppy, and a rule that overruled it would trade a judge error for a harness
error.

---

## The gold set

13 items over 11 chapters, 31 verbatim quotes.

- **Set A (10 items)** — standalone questions, fresh session, no history.
  Definitions the book states plainly: shadow, frictional force, gravitational
  force, sublimation, lever, sound, magnet poles, balanced diet, joints, inner
  planets.
- **Set B (2 items)** — pronoun follow-ups asked down a real session, after
  their topic question. *"How can we reduce it?"* and *"What happens when we
  bring two of them together?"* The pronoun names nothing, so these test whether
  `rag/followup.py` carried the topic into the search, and grading them is only
  meaningful against what that turn actually read.
- **Set C (1 item)** — off-syllabus. *"Who won the 2022 football world cup?"*
  must retrieve nothing and cite no page. Scored on citations, not on text.

Two items are traps by construction:

- **`B2-magnets-together`** — word overlap cannot separate "like poles repel"
  from "like poles attract". This item is what distinguishes a real judge from
  an overlap score.
- **`A9-joints`** — the evidence is split across four chunks, three of them
  figure-caption fragments under 80 characters. It is in the set precisely
  because a two-passage budget cannot carry all of it.

### Every item also ships a reference answer

Each item carries an answer written **only** from its gold evidence, in the
tutor's own style. These are not scored against the model. They are the set's
own integrity check: a reference answer must cover its own key phrases, and the
harness verifies this. It catches the failure mode that quietly ruins a key
phrase list — a phrase so literal that no correct answer could ever match it.

That check has already earned itself: `"in contact"` was never going to match
*"come into contact"*, and `"fall to the ground"` was never going to match
*"fall towards the ground"*.

---

## What the first run found

Run `v1` (`results/groundedness-v1-9ce3cc50.md`), 2026-09-16, tutor
`qwen2.5:1.5b`, judge `gemma3:4b`, backend defaults (`top_k` 2,
`rag_context_max_chars` 800, `rag_passage_max_chars` 600, temperature 0.3).

| | |
|---|---|
| Groundedness | **71%** — 25 of 35 claims supported |
| Contradictions | 0 by the judge; the known-error patterns also fired 0 times |
| Key coverage | 62% |
| Context recall | **38%** — of 31 gold quotes, most never reached the prompt |
| Fully grounded turns | 6 / 12 |
| Off-syllabus abstention | held — 0 sources, no page cited |

**The bottleneck is retrieval, not the model.** Context recall of 38% is the
headline number, not groundedness. On 5 of 12 turns the gold passage did not
reach the prompt *at all* — and the model is not going to ground an answer in
text it was never shown. Three specific causes, each visible in the report:

1. **Exercise pages outrank the definitions they are asking about.** For *"What
   are the poles of a magnet?"* the top passage is p.121 — a fill-in-the-blanks
   page reading *"There is repulsion between the .......... poles of a magnet,
   and attraction between its ............ poles."* The answer has been
   **removed by the publisher**, and the tutor filled the blanks itself. On the
   follow-up it produced *"When two poles of opposite charges are brought close
   to each other, they repel each other"* — exactly backwards. This confirms the
   mechanism recorded in exp006 and shows it surviving the current settings.
   These pages are near-duplicates of the definition in embedding space, so no
   distance threshold separates them; **they need filtering at ingest.**
2. **The answer is fragmented across chunks too small to rank.** For *"What are
   the types of joints in our body?"* the words *movable* and *immovable* live in
   two figure-caption chunks under 80 characters. Neither ranks. The tutor
   supplied *"fibrous joints and cartilaginous joints"* from its own memory —
   Class 11 anatomy, fluent, and not what the book teaches.
3. **`top_k` 2 with an 800-character budget is `top_k` 1 in practice.** 7 of the
   12 scored turns read a single passage. When that one passage is an exercise
   stub, the turn has nothing else to work with.

**Four turns were "right, but not from the book"** — `A3-gravity`,
`A4-sublimation`, `A9-joints`, `A10-inner-planets`. `A10` is the cleanest
example: asked which planets are the inner planets, the tutor answered *"Mercury,
Venus, Earth, and Mars"* — correct, and its key coverage is 100% — while the
sentence that says so never reached the prompt. Those four turns look perfect in
the UI. The retrieval pipeline contributed nothing to any of them, and **no
retrieval metric and no human spot-check would have shown that.**

**The abstention gate works; it is not a safety net.** The off-syllabus question
correctly retrieved nothing and cited no page. The tutor then answered from its
own knowledge that *"The 2022 World Cup was won by the United States team"*,
which is false. The gate protects the book's integrity, not the student — worth
separating, because the gate passing is easy to misread as the question being
handled.

### What was done about it, and what it bought

All three fixes above were implemented at ingest
(`apps/backend/app/services/rag/quality.py`, `RAG_FILTER_CORPUS`), the book was
re-ingested (447 -> 327 chunks) and the same evaluation re-run.

Run `v2-filtered` (`results/groundedness-v2-filtered-7c700616.md`), same tutor,
same judge, same settings, only the corpus changed:

| | v1, unfiltered | v2, filtered |
|---|---|---|
| Groundedness | 71% | **87%** |
| Key coverage | 62% | **75%** |
| Context recall | 38% | **51%** |
| Fully grounded turns | 6 / 12 | **9 / 12** |
| grounded and complete | 6 | **9** |
| right, but not from the book | 3 | **1** |
| ungrounded and incomplete | 2 | **0** |

The three specific failures named above are gone:

* **magnets** -- the p.121 fill-in-the-blanks page no longer exists in the
  corpus, and the p.117 definition is now the top hit at distance 0.230.
  `A7-magnet-poles` went from 0% to 100% key coverage.
* **sublimation** -- the p.51 question stub ("4. What is sublimation ? Write
  the") is gone and both remaining passages carry the definition; context recall
  0% -> 100%.
* **joints** -- `A9-joints` went from "right, but not from the book" at 50%
  groundedness to "grounded and complete" at 100%.

Two things did **not** improve, stated because a table of wins is not a result:

* **`A10-inner-planets` got worse.** Re-chunking moved "Mercury, Venus, Earth
  and Mars are the inner planets" into a chunk that no longer ranks first, so
  the turn is still "right, but not from the book". Filtering fixed retrieval
  competition; it does nothing for chunk boundaries, which is the next lever.
* **`A4-sublimation` reads worse** despite now having perfect context recall:
  the tutor wrapped the correct definition in an invented ice/water-vapour
  analogy. That is a generation problem, and this is the first run where the
  evaluation can say so with confidence, because the excerpt it read is known to
  have contained the answer.

Context recall at 51% is still the number to attack next, and the remaining
cause is chunking rather than corpus noise.

---

## Known limitations

Stated plainly, because a metric whose limits are unlisted gets over-read.

1. **Sentence-granularity claims.** A half-true compound sentence gets one
   verdict, usually awarded to the supported half. Claim #2 in the worked
   example above is exactly this.
2. **A 4B judge has a 12% false-support rate.** Printed every run. Treat any
   single verdict as indicative; treat the aggregate as the measurement.
3. **Key coverage is literal phrase matching.** It is deterministic and
   auditable, which is why it is not a model — but it will miss a correct answer
   phrased in an unanticipated way. The reference-answer check bounds how badly.
4. **One run is not a measurement.** The tutor samples at temperature 0.3, so
   per-item scores move between identical runs. Across two runs of set A,
   `A3-gravity` moved 33 points (100% → 67%) and `A4-sublimation` moved 17
   (33% → 50%), while the set aggregate moved 3 (76% → 73%). Track the
   aggregate; read the per-item detail as diagnosis, not as a score.
5. **13 items is a diagnostic set, not a benchmark.** It was sized to be
   hand-authored from the book with every quote verified. It finds failure
   modes; it does not measure a percentage to one decimal place.

---

## Reproducing a run

```bash
ollama serve                                              # qwen2.5:1.5b + gemma3:4b
cd apps/backend && OLLAMA_MODEL=qwen2.5:1.5b PORT=8756 ./run.sh
python3 scripts/eval/groundedness_eval.py --label v1
```

The harness refuses to start if the library is closed or if any gold quote has
stopped matching the corpus — a re-ingest with different chunk settings can
split a quote across two chunks, and context recall would then silently read
zero for a turn that read exactly the right page.

Each run writes three files to `results/`:

- `run-<label>-<id>.json` — the raw transcript, saved **before** judging, so
  `--rescore` can re-judge minutes of generation without asking the tutor again
- `groundedness-<label>-<id>.md` — every claim under the excerpt it was judged
  against, so a verdict can be overruled by a person with the book open
- `groundedness.csv` — one row per turn, appended across runs

Tutor turns and judge calls run in two separate phases. Ollama holds one model
at a time on this hardware, so alternating between them reloads both on every
item.
