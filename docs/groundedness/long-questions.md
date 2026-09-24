# Long questions — what changes when a Class 6 student talks like a Class 6 student

**Date:** 23 Sep 2026 · **Tutor:** `qwen2.5:1.5b` @ 127.0.0.1:8756, backend defaults (top_k 2, budget 800, passage cap 600, temp 0.3) · **Judge:** `gemma3:4b`
**Corpus:** `apps/backend/data/library.db` — 7 documents / 5,091 chunks, of which 898 are Class 6 Science (MSCERT `Class6_Sci_book.pdf` + NCERT `Class06-Science`)
**Gold set:** [`evalset-long.json`](evalset-long.json), 12 items · **Full report:** [`results/groundedness-long-q-v1-805e1ef6.md`](results/groundedness-long-q-v1-805e1ef6.md) · **Transcript:** `results/run-long-q-v1-805e1ef6.json`
**Control:** [`results/groundedness-short-q-control-6e57e523.md`](results/groundedness-short-q-control-6e57e523.md) — the existing short set re-run on the same corpus, so the comparison below is not confounded by the 7-book re-ingest
**Device:** dev Mac (Intel i7-9750H, 16 GB). Nothing here was run on the target laptop.

## Why a second gold set

Every item in [`evalset.json`](evalset.json) is a bare definition question of 16–48 characters — "What is a shadow?", "What is a lever?". None of them asks for two things, and none carries a sentence of story before the question. Three parts of the pipeline only come under load when they do:

- what a long, chatty query embeds to, and therefore which passage ranks first;
- whether the two or three passages a compound question needs fit inside `rag_context_max_chars` (800) at `rag_top_k` (2);
- whether a 1.5B model answers every part of a compound question, or only the part its excerpt happens to cover.

So this set is 12 items of 231–360 characters (mean 286), each a scene followed by a question asking for two or three things: rice with stones in it, the drops under a tea pan's lid, two bar magnets in a school bag, a bulb that did not glow, a crowbar on a brick, a long off-syllabus question, and a long follow-up. Style and scoring are unchanged from the short set, so the two are comparable turn for turn: same judge, same claim splitter, same `--check-evalset` verification (29 gold quotes byte-for-byte in the corpus, 11 reference answers covering their own keys).

## Headline

| | long set (12 items) | short set, same corpus (13 items) | short set, single-book corpus (v6, 22 Sep) |
|---|---|---|---|
| Groundedness (claims) | **78%** (57/73) | 97% (37/38) | 97% (38/39) |
| Contradictions | 3 claims, 3 of 11 turns | 0 | 0 |
| Key coverage | **47%** | 62% | 67% |
| Context recall | **33%** | 46% | 54% |
| Fully grounded turns | 3/11 | 11/12 | 11/12 |
| Passages read per turn | **1.0** | 1.17 | — |
| Off-syllabus abstention | held | held | held |
| Judge calibration | 8/14 (57%) | 11/14 (79%) | 11/14 (79%) |
| Prompt tokens, mean | 322 | 273 | — |
| Outcomes | 4 complete · 3 contradict · 2 thin · 2 ungrounded · 1 abstained | 8 complete · 3 thin · 1 abstained · 1 right-not-from-book | 8 complete · 3 thin · 1 abstained · 1 right-not-from-book |

The middle column is the control: the **short** set, re-run on the **same** 7-book corpus an hour after the long one, same tutor and judge. It exists because the published v6 baseline was measured on the old single-book corpus, so without it the drop could be blamed on the corpus re-ingest. It cannot be: the short set scores 97% / 62% / 46% on the 7-book corpus, within noise of its own single-book run. **The question length is what moves these numbers.**

(The control needed `--allow-corpus-drift`: one of `B2-magnets-together`'s two gold quotes no longer survives the current chunking, so that item's recall is understated by half. Its other item recalls are sound.)

Per item:

| item | asks for | grounded | key | recall | outcome |
|---|---|---|---|---|---|
| `L1-clean-rice` | 2 | 100% | 67% | 50% | grounded and complete |
| `L2-tea-pan-lid` | 2 | 100% | 75% | 50% | grounded and complete |
| `L3-fish-and-camel` | 3 | 67% | 25% | 50% | ungrounded and incomplete |
| `L4-two-bar-magnets` | 2 | 60% | **0%** | **0%** | contradicts the book |
| `L5-bulb-did-not-glow` | 3 | 83% | 25% | 67% | grounded but thin |
| `L6-where-rain-comes-from` | 2 | 83% | 100% | 33% | grounded and complete |
| `L7-only-rice-and-chapati` | 3 | 100% | 33% | 33% | grounded but thin |
| `L8-crowbar-three-parts` | 3 | 43% | 60% | **0%** | contradicts the book |
| `L9-drum-up-the-plank` | 2 | 80% | 50% | 33% | grounded and complete |
| `L10-bicycle-wheel` | 2 | 83% | 50% | 50% | contradicts the book |
| `L11-off-syllabus-metro` | — | — | — | — | abstained |
| `L12-concrete-colony` | 2 | 67% | 33% | **0%** | ungrounded and incomplete |

## 1. One passage arrives, and a compound question needs two

`rag_top_k` retrieved two passages on all 11 grounded turns. **One** reached the prompt, every time.

| | |
|---|---|
| Passage 1, after the 600-char cap | 299–698 chars (median 632) |
| Room left under the 800-char budget | 145–448 chars (median 168) |
| Grade-6 chunks that would fit in 168 chars | ~10% |
| Grade-6 chunks that would fit in the best case, 448 | 35% |

This is not something long questions cause. The short set on the same corpus reads 1.17 passages a turn — the budget drops the second one on 10 of its 12 grounded turns too. The chunk median is 554 characters and `rag_chunk_chars` is 700, so a second passage essentially cannot fit behind a first one of any normal size, whatever the question. It is the config's own prediction: `rag_context_max_chars` says "most turns now carry one passage, so which passage ranks first matters more than it did".

What changes is the consequence. A short definition question needs one passage and gets it. A compound question needs two or three, and the second half of its answer is in the passage that gets cut:

- **L5** read p.119's "direction of current / fused bulb" chunk. The chunk that defines a circuit as "a complete path for electricity to pass" was retrieved second and cut. The answer then defined a circuit as "a path that allows electricity to flow from one point to another" — its own words, not the book's.
- **L8** read a p.88 chunk about wheels, axles and pulleys. p.86 — "A lever has three parts, namely, effort, load and fulcrum" — was retrieved second and cut. Both pages were cited to the student; only one was read.
- **L1** asked about stones *and* dust. Both hits were the same p.38 page about washing; handpicking is on p.36 and never came.

Three questions asked for three things. No turn in this set ever had more than one passage's worth of book in front of it.

## 2. What the model does with the half it did not get

It fills the gap from itself, in the tutor's voice, with no marker that the book stopped:

- **L3** (habitat and adaptation): gills, a streamlined body, thick fur and a fat-storing hump. None of that is in the excerpt. It also defines adaptation as "the process by which an organism changes its characteristics", which is not what the book says ("the presence of specific features or certain habits"). The book's definition of *habitat* — "the place where organisms live" — never reaches the answer at all.
- **L8**: invents a machine. "A fulcrum is a machine part that acts as a fulcrum… The three parts of a fulcrum machine are the fulcrum, the effort arm, and the load arm", and the fulcrum is identified as the iron rod rather than the brick. The book's three parts are effort, load and fulcrum.
- **L12** (the follow-up): gives the school "Green Roofs and Rain Gardens" as one of the book's two techniques. The book's second technique is letting water into the ground from roadside drains.
- **L9**: "an axe is like a flat ramp". The book: a wedge is two inclined planes joined.
- **L10**: answers the question, then appends an unasked paragraph about speed and a bus from Solapur to Pune, because the retrieved chunk ran on into the next section.

## 3. The magnet polarity regression is back, and the net missed it

**L4** answers: "These poles are near the ends of the magnet **and attract each other**. When you bring two magnets close, their poles attract each other." It never says like poles repel. The student is taught the opposite of p.108.

Two things failed to catch it:

1. Retrieval ranked a 299-char NCERT stub first ("Poles of a magnet are said to be near these ends. Try and bring a few magnets of different shapes to the classroom."). The MSCERT passage carrying the rule — "There is repulsion between like poles of a magnet, while there is attraction between the opposite poles" — never entered the top 2. Context recall 0/2.
2. The `forbidden_claims` patterns are written for "like poles attract" / "opposite poles repel". The model wrote "their poles attract each other", which no pattern matches.

Three of its five claims were then marked **supported** — against "Poles of a magnet are said to be near these ends", a sentence that cannot contradict anything. Only **key coverage 0%** caught it.

## 4. Groundedness stops being the right instrument at this length

This is the most important caveat on the 78% above. When the excerpt is one passage that answers a fraction of the question, a wandering answer is graded against text too thin to contradict it, so it scores as supported:

- **L8**, whose answer is invented end to end, scored 43% — three of its claims were marked supported against lines about axles and bicycle pedals.
- **L3**'s camel hump was marked supported against the general definition of adaptation.
- All three "contradicted" verdicts are judge slips: on L4 and L10 it quoted the claim back to itself as its evidence, and on L8 it called a roughly-true statement about levers a contradiction of a sentence about bicycle pedals. The substantive contradiction count is closer to one (L4's polarity), and that one is recorded as *supported*.

The judge's own calibration on this set is 8/14 (57%), missing real support 0% of the time and waving a false claim through 12%. Its errors on the short set were one-directional and harmless (a polarity flip landing as *unsupported*); at this length it also over-calls contradiction. Both directions are now in play, so contradiction counts from this set need reading by hand.

**On long questions, read key coverage (47%) and context recall (33%), not groundedness.** Those two say what happened: the book's answer mostly did not arrive, and less than half of what the book answers with came out.

## 5. Abstention held on citations, not on the answer

**L11** (350 characters naming a metro line, a state government and a Chennai coach factory) retrieved nothing and cited nothing — the distance threshold was not defeated by length, which was the risk being tested. But the model still answered, and it affirmed the premise the question handed it: "The coaches for the metro trains are made by a big factory near Chennai, which specializes in producing high-quality coaches for public transport systems." The harness scores abstention on citations, so this passed. A long question that asserts something false is a hallucination route the current check does not see.

## 6. Latency

Not the problem, at least not on this machine. The long question itself is cheap; the long answer is not.

| | long set, mean (range) | short set, mean |
|---|---|---|
| Prompt tokens | 322 (182–367) | 273 |
| Prefill | 2.50 s (1.15–4.32) | 1.11 s |
| ms per prompt token | 7.7 (median 6.8) | 4.0 (median 3.8) |
| Time to first token | 3.3 s (1.5–6.5) | — |
| Completion tokens | 132 (77–266) | 68 |
| Generation | 10.2 s (4.4–29.1) | — |
| Answer length | 635 chars (410–1,394) | 332 chars |

The solid number is **+49 prompt tokens**, which on the target's 25.6 ms/token is ~1.3 s of extra prefill. The per-token prefill difference (7.7 vs 4.0 ms) is *not* attributable to question length from this data: the two runs were sequential rather than interleaved, and the long one ran with `gemma3:4b` still resident from a `--selftest`, so machine state differed. Do not carry that ratio to the target; re-measure there if it matters.

What did double is the **answer**: 132 completion tokens against 68, and 635 characters against 332. L12 alone produced 266 tokens and 29 s of generation. A compound question pulls a compound answer, and on the target at 15.6 tok/s that is the cost that would be felt — 132 tokens is ~8.5 s of generation before the student has the whole reply.

## What this suggests, in order of expected effect

1. **Let a compound question buy a second passage.** The budget is one number for two jobs — bounding prefill and bounding how much book arrives. Raising `rag_context_max_chars` to ~1,300 when the question asks for more than one thing costs ~12 s of prefill on the target at 25.6 ms/token, which is too much as it stands; lowering `rag_passage_max_chars` so two trimmed passages fit inside 800 is the cheaper version of the same idea, and `retrieval.shorten_passage` already picks the sentences that match the question. Worth a sweep: cap 400 × top_k 2 against the current 600 × 1-in-practice.
2. **Say when the book ran out.** Every fabrication in §2 is delivered in the same voice as the grounded half. The prompt could require the model to name what it could not find; a 1.5B model may not comply, which is itself worth measuring.
3. **Fix the magnet page ranking.** A 299-char activity stub ("Try and bring a few magnets… to the classroom") outranked the passage with the rule. This is the exercise/apparatus filtering problem from the ingestion notes, now visible on the NCERT half of the Class 6 corpus rather than the MSCERT half. `rag_exercise_page_ratio` was calibrated on the MSCERT book only.
4. **Widen `forbidden_claims` beyond the book's own wording.** "their poles attract each other" is what a model actually writes; "like poles attract" is what the book would have to write to be wrong.
5. **Score the off-syllabus turn on the answer, not only on the citation.** L11 passed while asserting an invented fact.

## Reproducing

```bash
# verify the gold set against whatever is in library.db right now
python3 scripts/eval/groundedness_eval.py --evalset docs/groundedness/evalset-long.json --check-evalset

# grade the judge on this set's 14 known verdicts
python3 scripts/eval/groundedness_eval.py --evalset docs/groundedness/evalset-long.json --selftest

# the run above (backend must be up: cd apps/backend && ./run.sh)
python3 scripts/eval/groundedness_eval.py --evalset docs/groundedness/evalset-long.json --label long-q-v1

# the short-question control on the same corpus (one gold quote has drifted)
python3 scripts/eval/groundedness_eval.py --label short-q-control --allow-corpus-drift

# re-judge without paying for generation again
python3 scripts/eval/groundedness_eval.py --evalset docs/groundedness/evalset-long.json \
    --rescore docs/groundedness/results/run-long-q-v1-805e1ef6.json --label long-q-v1-rescored
```
