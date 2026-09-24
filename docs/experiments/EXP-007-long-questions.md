# EXP-007 — Long, compound questions against the RAG pipeline (qwen2.5:1.5b)

**Approach:** English-only
**Owner:** Mayur | **Date started:** 23 Sep 2026
**Date closed:** 23 Sep 2026 | **Status:** Worked — the hypothesis held, and the mechanism behind it is identified and measured
**Device tested on:** Dev machine only — Intel Mac, Core i7-9750H (6 cores, AVX2), 16 GB, macOS 26.6.2. Nothing was run on the 8 GB Windows target laptop; the target figures quoted below are projections from exp005/exp006 measurements on it.
**Related experiments:** exp004 (groundedness marking) · exp006 (context-budget sweep, where the 800-character budget was chosen) · Groundedness harness v1–v6, 16–22 Sep (the instrument) · NCERT 7-book ingest, 22 Sep (the corpus this ran on) · EXP-XXX small-model shortlist (still unnumbered — if that one becomes 007, renumber this to 008)

---

## 1. Context

The tutor answers from the textbook through RAG: retrieve at `rag_top_k` = 2, trim each passage to `rag_passage_max_chars` = 600, cap the whole excerpt block at `rag_context_max_chars` = 800, then generate with `qwen2.5:1.5b` at temperature 0.3.

Both of those caps were chosen for latency on the target laptop, in exp006: 800 characters bought a 0.66 s mean improvement in time-to-first-token over 1200, and no answer the book held was lost at the time. The config comment recorded the side effect honestly — "most turns now carry one passage, so which passage ranks first matters more than it did."

Quality was measured by the groundedness harness. After the textbook-ingest re-ingest, run v6 (22 Sep) scored 97% groundedness, 0 contradictions, 67% key coverage and 54% context recall over the Class 6 book. That looked close to solved.

The gap was in the gold set, not the pipeline. Every one of the 13 items in `docs/groundedness/evalset.json` is a bare definition question of 16–48 characters — "What is a shadow?", "What is a lever?", "Which are the inner planets?". Not one of them asks for two things, and not one carries a sentence of story before the question. A Class 6 student does not talk like that. They say "my mother bought rice and it had stones in it, what two methods should we use and how do they work".

Three parts of the pipeline only come under load when a question is long and compound, and none of them had ever been measured:

- what a long, chatty query embeds to, and therefore which passage ranks first;
- whether the two or three passages a compound question needs can fit inside an 800-character budget at top_k 2;
- whether a 1.5B model answers every part of a compound question, or only the part its excerpt happens to cover.

On top of that, the corpus had changed underneath the last measurement: `library.db` now holds 7 documents and 5,091 chunks (2 books and 898 chunks in Class 6 Science alone), where v6 was measured on one book and 373 chunks. Any new number would need a control run to tell corpus effects from question-length effects.

## 2. Hypothesis

*If the same pipeline is asked questions of 230–360 characters that each ask for two or three things, then key coverage and context recall will fall well below the short-question baseline of 62% / 46%, because at `rag_top_k` 2 with an 800-character budget only one passage ever reaches the prompt and one passage cannot hold the answer to a three-part question.*

The reasoning underneath it:

- **Arithmetic on the budget.** `rag_passage_max_chars` is 600 and `rag_chunk_chars` is 700. If passage 1 arrives anywhere near full size, there are 200 characters or fewer left under the 800-character cap, and the median grade-6 chunk is 554 characters. A second passage therefore has almost nowhere to go. The config already predicted one-passage turns; the question was what that costs when the student asks for more than one thing.
- **Embedding dilution.** A 286-character query with a scene in front of it averages the scene's vocabulary into the query vector. exp004 already saw retrieval wander on short follow-ups with dangling pronouns; a long query is the same problem from the other direction, with too much text rather than too little.
- **What a 1.5B model does with a gap.** exp004 and exp006 both recorded the model overriding correct passages and asserting things the excerpt did not contain (joints "of three types" when the book said two). Given an excerpt that answers one third of the question, the likely behaviour is to answer the rest from its own weights, in the same voice, with no marker that the book stopped.

## 3. Why this approach over the alternatives

| Option considered | Why not chosen |
| --- | --- |
| Reuse `evalset.json` and just sweep the budget again | Sweeping the budget on short definition questions is exactly what exp006 did. A short question needs one passage and gets it, so a budget sweep on that set cannot show what a compound question loses. The question shape is the variable under test, not the budget. |
| Generate the long questions with an LLM | The gold evidence has to be byte-for-byte what `library.db` holds, or `--check-evalset` fails and context recall silently reads zero. Model-written questions drift from the book's own wording and quietly become questions the book does not answer, which measures the question writer rather than the tutor. |
| Take real long questions from user logs | `turn_log_enabled` deliberately records shapes and durations only, never question or answer text, because those CSVs get copied off classroom laptops. There is no log of real questions to draw from, by design. |
| Only judge by hand, no harness | Hand-marking does not produce comparable numbers across runs, and the instrument already exists. Using the same judge, splitter and claim rules as the short set is what makes the two directly comparable. |
| Raise the budget first, then measure | That inverts the order. Raising `rag_context_max_chars` to 1300 costs roughly 12 s of prefill on the target at 25.6 ms/token. Worth paying only if the one-passage ceiling is shown to be what is actually hurting; this experiment is what shows it. |

## 4. What we did — step by step

1. **Read the corpus, not the PDFs.** Dumped all 898 Class 6 Science chunks out of the live store so every gold quote could be taken from the text retrieval can actually return, rather than from the page as a human reads it.

    ```
    sqlite3 apps/backend/data/library.db \
      "select document_id, ordinal, page_start, heading, text from chunks where document_id in (1,3) order by document_id, ordinal"
    ```

2. **Wrote 12 items** into `docs/groundedness/evalset-long.json`, 231–360 characters each (mean 286): 10 scored compound questions across separation of substances, evaporation/condensation, habitat and adaptation, magnets, electric circuits, the water cycle, balanced diet, levers, inclined planes and types of motion; 1 long off-syllabus item that must abstain; 1 long follow-up asked after "What is rainwater harvesting?" in the same session. Each item carries gold quotes, a reference answer written only from those quotes, an answer key (`required_facts`), and known-error patterns (`forbidden_claims`).

3. **Verified the set against the live corpus** before trusting any number from it.

    ```
    python3 scripts/eval/groundedness_eval.py --evalset docs/groundedness/evalset-long.json --check-evalset
    # gold set checks out: 29 quotes verbatim in the corpus, 11 reference answers cover their own keys.
    ```

    This caught one real bug on the first pass: the known-error pattern `north pole[^.]{0,30}points to the south` fired on the item's own reference answer, because the book's sentence reads "…is called the north pole while the end that points to the south…". Tightened to `north pole (is|means) the end (that |which )?points to(wards)? the south`. Without that check the harness would have marked a correct answer as a contradiction.

4. **Graded the judge before grading the tutor**, on 14 new calibration statements keyed to this set's evidence.

    ```
    python3 scripts/eval/groundedness_eval.py --evalset docs/groundedness/evalset-long.json --selftest
    # accuracy 57% | missed real support 0% | waved a false claim through 12%
    ```

5. **Ran the long set** against the already-running backend. 12 items, 13 generations (the follow-up needs its topic turn first, down the same session, or the pronoun has no antecedent).

    ```
    python3 scripts/eval/groundedness_eval.py --evalset docs/groundedness/evalset-long.json --label long-q-v1
    ```

6. **Ran the short set as a control on the same corpus.** This was not in the original plan and is the step that makes the result interpretable: the published v6 baseline was measured on the old single-book corpus, so without this the drop could be blamed on the 7-book re-ingest.

    ```
    python3 scripts/eval/groundedness_eval.py --label short-q-control --allow-corpus-drift
    ```

    `--allow-corpus-drift` was needed because one of `B2-magnets-together`'s two gold quotes no longer survives the current chunking. That item's recall is understated by half in the control; the other 11 are sound.

7. **Reconstructed the retrieval mechanics from the transcripts** — how many passages each turn actually read, how much room was left under the budget, and what the dropped passage contained — by matching the run JSON's sources back to chunk lengths in `library.db`.

**Environment**

- Model / library and exact version: tutor `qwen2.5:1.5b` (Q4_K_M) on Ollama 0.32.15; judge `gemma3:4b`, local, through the same Ollama; embeddings `nomic-embed-text`, 768 dims
- Runtime and build flags: backend defaults — `rag_top_k` 2, `rag_context_max_chars` 800, `rag_passage_max_chars` 600, `rag_chunk_chars` 700, `rag_chunk_overlap_chars` 105, `rag_max_distance` 0.42, `temperature` 0.3, `max_tokens` 400, `num_ctx` 4096, `history_questions` 1
- Hardware and OS build: Intel i7-9750H, 6 cores, 16 GB, macOS 26.6.2 (dev machine, not the target)
- Corpus: `apps/backend/data/library.db`, 7 documents / 5,091 chunks; 898 of them Class 6 Science (MSCERT `Class6_Sci_book.pdf` + NCERT `Class06-Science`)
- Baseline we compared against: the short gold set `docs/groundedness/evalset.json`, re-run on the same corpus on the same day (`short-q-control`), with the older single-book run v6 quoted alongside

## 5. What we measured

| Metric | Baseline (short set, same corpus) | After (long set) | Target | Met? |
| --- | --- | --- | --- | --- |
| Groundedness, claims supported | 97% (37/38) | **78%** (57/73) | no regression | No |
| Key coverage | 62% | **47%** | no regression | No |
| Context recall | 46% | **33%** | no regression | No |
| Contradictions | 0 claims, 0 of 12 turns | 3 claims, 3 of 11 turns | 0 | No |
| Fully grounded turns | 11/12 | 3/11 | — | No |
| Passages read per turn | 1.17 | **1.0** | 2 | No |
| Off-syllabus abstention | held | held | held | Yes |
| Judge calibration | 11/14 (79%) | 8/14 (57%) | — | No |
| End-to-end latency (TTFT, dev Mac) | 1.4 s mean (0.4–4.7) | 3.3 s mean (1.5–6.5) | under 4.1 s on target | Dev machine — does not transfer, see note |
| Prompt tokens, mean | 273 | 322 | — | +49 |
| Completion tokens, mean | 68 | 132 | — | +94% |
| Answer length, mean | 334 chars | 635 chars | — | +90% |
| Peak RAM | not measured | not measured | — | — |
| Package size | not measured | not measured | — | — |

How these were measured:

- **Quality metrics** — one run each, no averaging. Every claim is graded by `gemma3:4b` against the excerpt block that turn actually read (`return_context=true`), never against the pages it cited, because the budget routinely cuts a cited passage before the prompt. Claims are sentences minus the ones that assert nothing (questions, and the second-person invitation the style rule mandates). Both runs used the same judge, the same splitter and the same corpus, an hour apart.
- **Key coverage** is string containment of the answer key's accepted phrasings, so it is deterministic and does not depend on the judge.
- **Context recall** is byte-for-byte containment of the gold quote in the excerpt block, verified in advance to exist in the corpus.
- **Latency** is Ollama's own `prompt_eval_duration` / `eval_duration` per turn from the run transcripts, and `ttft_ms` from `apps/backend/logs/turns-backend.csv`; single run, warm model except one load per run. The two runs were **sequential rather than interleaved**, and the long one ran with `gemma3:4b` still resident from a `--selftest`, so the millisecond gap between them is not cleanly attributable to question length — per-token prefill reads 7.7 ms against 4.0 ms, which is far more than +49 tokens can explain. The number that does transfer to the target is the token count. Re-measure on the target laptop before quoting any of these milliseconds.
- **Passages read** counts `[n]` markers in the excerpt block actually sent to the model, not the number of hits retrieved.

## 6. What worked

**The set itself discriminates.** Same tutor, same judge, same corpus, same day: short questions score 97% / 62% / 46% and long questions score 78% / 47% / 33%, with 3 of 11 turns flagged as contradicting the book against 0 of 12. The control is what earns that statement — the short set's 97% on the 7-book corpus is within noise of its 97% on the single-book corpus, so the corpus re-ingest is not the cause and the question shape is.

**Verifying the gold set before running it caught a real defect.** The `--check-evalset` pass rejected a known-error pattern that fired on its own reference answer. Mechanism: the pattern was written from the shape of the error rather than the shape of the book's sentence, and the book's sentence contains the error's words in a different order. Any run using that pattern would have scored a correct answer as a contradiction.

**Abstention held at length, which was the specific risk being tested.** A 350-character off-syllabus question naming a metro line, a state government and a Chennai coach factory retrieved nothing and cited nothing. Mechanism: `rag_max_distance` 0.42 was calibrated on the gap between on-topic (0.12–0.34) and off-topic (0.50–0.58) queries, and averaging more off-topic text into the query vector moved it further from the textbook chunks, not closer. Length does not defeat the threshold.

**Prefill accounting from token counts rather than milliseconds.** The only latency number that transfers to the target laptop is the token count, and a long question costs +49 prompt tokens, about 1.3 s of extra prefill at the target's measured 25.6 ms/token. The milliseconds measured on the Mac do not transfer and are not claimed to.

## 7. What didn't work

**Failure 1 — one passage reaches the prompt, and a compound question needs two**

- Symptom: all 11 grounded long turns retrieved 2 passages and read exactly 1. On L5 the answer defined an electric circuit in its own words; on L8 the answer invented a machine; on L1 half the question was never addressed.
- What we tried: reconstructed each turn's excerpt block against `library.db` to see what the dropped passage held. Passage 1 after the 600-character cap ran 299–698 characters (median 632), leaving 145–448 characters (median 168) under the 800-character budget. About 10% of grade-6 chunks would fit in 168 characters; 35% would fit in the best case of 448. The median chunk is 554.
- Root cause: identified, and it is arithmetic, not a bug. `rag_passage_max_chars` 600 and `rag_context_max_chars` 800 cannot both be satisfied by two passages drawn from a corpus whose median chunk is 554. The short set reads 1.17 passages a turn under the same config, so this is not caused by long questions — but a short definition question needs one passage and a three-part question needs three. The specific losses: L5's "complete path" definition of a circuit was retrieved second and cut; L8's p.86 chunk holding "A lever has three parts, namely, effort, load and fulcrum" was retrieved second, cut, **and still cited to the student**; L1's handpicking passage is on p.36 and never entered the top 2 at all.
- Dead end or parked? Parked with a concrete next step: lower `rag_passage_max_chars` so two trimmed passages fit inside 800, rather than raising the budget. `retrieval.shorten_passage` already selects the sentences that best match the question, so a 400-character cap keeps the matching sentences and makes room. Raising the budget to 1300 would cost roughly 12 s of prefill on the target and is not affordable as things stand.

**Failure 2 — the model fills the missing half from its own weights, in the tutor's voice**

- Symptom: fabricated content presented identically to grounded content, with no marker that the book ran out. L3 supplied gills, a streamlined body, thick fur and a fat-storing hump, none of which is in the excerpt, and defined adaptation as "the process by which an organism changes its characteristics" rather than the book's "presence of specific features or certain habits". L8 invented a "fulcrum machine" and identified the fulcrum as the iron rod rather than the brick. L12 gave the school "Green Roofs and Rain Gardens" as one of the book's two techniques. L9 called an axe "a flat ramp". L10 answered correctly and then appended an unasked paragraph about speed and a bus from Solapur to Pune, because the retrieved chunk ran on into the next section.
- What we tried: nothing yet — this run was diagnostic. The prompt currently has no instruction to say when the book does not cover something.
- Root cause: partially identified. The immediate cause is Failure 1 — the excerpt answers a fraction of the question. Whether a prompt instruction would suppress it on a 1.5B model is **not known** and needs its own test; exp004 recorded this model overriding evidence it did have, which is not encouraging.
- Dead end or parked? Parked. Next test: add a "say what you could not find in the book" clause and re-run this set.

**Failure 3 — the magnet polarity error is back, and two separate nets missed it**

- Symptom: L4 answers "These poles are near the ends of the magnet **and attract each other**. When you bring two magnets close, their poles attract each other." It never states that like poles repel. A student is taught the opposite of p.108. Key coverage 0%, context recall 0/2.
- What we tried: traced what ranked first. A 299-character NCERT activity stub ("Poles of a magnet are said to be near these ends. Try and bring a few magnets of different shapes to the classroom.") took the top slot; the MSCERT passage carrying the rule — "There is repulsion between like poles of a magnet, while there is attraction between the opposite poles" — never entered the top 2.
- Root cause: identified, two independent causes. (a) `rag_exercise_page_ratio` 0.40 was calibrated on the MSCERT book only, and the NCERT half of the Class 6 corpus contributes activity stubs that outrank definitions — the same failure mode as the 16 Sep exercise-page problem, in a book the filter was never measured against. (b) The `forbidden_claims` patterns are written in the book's wording ("like poles attract", "opposite poles repel"), and the model wrote "their poles attract each other", which no pattern matches.
- Dead end or parked? Parked, and it is the highest-value follow-up: re-measure the corpus filter against the NCERT books with `scripts/eval/corpus_filter_report.py`, and widen the known-error patterns to what a model actually writes rather than what the book would have to write to be wrong.

**Failure 4 — groundedness-against-excerpt stops being the right instrument at this length**

- Symptom: 78% overstates fidelity. L8, whose answer is invented end to end, scored 43%, with three of its claims marked *supported* against lines about axles and bicycle pedals. L3's camel hump was marked supported against the general definition of adaptation. All three "contradicted" verdicts are judge slips: on L4 and L10 the judge quoted the claim back to itself as its own evidence. The one substantive content error in the run — L4's polarity — is recorded as *supported*.
- What we tried: graded the judge on 14 known verdicts before the tutor, as every run does. It scored 8/14 here against 11/14 on the short set, missing real support 0% of the time and waving a false claim through 12%.
- Root cause: identified. When the excerpt is one passage answering a fraction of the question, there is not enough text in it to contradict a wandering answer, so loosely-related claims land as supported. Separately, the judge's error direction changed: on the short set its mistakes were one-directional and harmless (a polarity flip landing as *unsupported*), and at this length it also over-calls contradiction. Both directions are now in play.
- Dead end or parked? Not a dead end, a reading rule: **on long questions read key coverage and context recall, not groundedness**, and read contradiction counts by hand. Those two metrics are deterministic string containment and do not depend on the judge.

**Failure 5 — abstention is scored on citations, not on the answer**

- Symptom: L11 retrieved nothing and cited nothing, which the harness scores as a pass, but the model still answered and affirmed the premise the question handed it: "The coaches for the metro trains are made by a big factory near Chennai, which specializes in producing high-quality coaches for public transport systems."
- What we tried: nothing — found by reading the transcript, not by any metric.
- Root cause: identified, and it is in the harness, not the tutor. `must_abstain` items are scored on whether sources were cited. A long question that asserts something false gets that assertion echoed back as fact, and no metric sees it.
- Dead end or parked? Parked. The check should also score the off-syllabus answer's text, not only its citation list.

## 8. Error logs

Raw and unedited except where marked.

### 8.1 Judge calibration, long set — 8/14

```
  ok calL-01        expected supported     got supported     When water is added to a mixture and the heavier par
  XX calL-02        expected contradicted  got supported     Decantation is the name for the heavier part of the
  ok calL-03        expected contradicted  got contradicted  Condensation is the conversion of liquid water into
  ok calL-04        expected supported     got supported     Steam touching a cold surface turns back into liquid
  ok calL-05        expected supported     got supported     A habitat provides an organism with food, water, air
  XX calL-06        expected unsupported   got contradicted  A fish can survive out of water for several hours by
  XX calL-07        expected contradicted  got unsupported   Two north poles brought close to each other pull tow
  ok calL-08        expected supported     got supported     The end of a bar magnet that points north is called
  XX calL-09        expected contradicted  got unsupported   In an electric circuit the current is taken to flow
  ok calL-10        expected unsupported   got unsupported   An electric cell of this kind supplies about 1.5 vol
  ok calL-11        expected supported     got supported     A lever has three parts: the effort, the load and th
  XX calL-12        expected contradicted  got unsupported   The fulcrum of a lever is the weight that the lever
  XX calL-13        expected contradicted  got unsupported   The steeper the inclined plane, the less weight we h
  ok calL-14        expected supported     got supported     Water vapour high in the air condenses into tiny dro

accuracy 57% | missed real support 0% | waved a false claim through 12%
```

### 8.2 Long-set per-item results

```
item                  grnd    key recall   clm   bad  outcome
------------------------------------------------------------------------------
L1-clean-rice        100%   67%   50%      8     0  grounded and complete
L2-tea-pan-lid       100%   75%   50%      7     0  grounded and complete
L3-fish-and-camel     67%   25%   50%      6     2  ungrounded and incomplete
L4-two-bar-magnets    60%    0%    0%      5     2  contradicts the book
L5-bulb-did-not-glow  83%   25%   67%      6     1  grounded but thin
L6-where-rain-comes-  83%  100%   33%      6     1  grounded and complete
L7-only-rice-and-cha 100%   33%   33%      5     0  grounded but thin
L8-crowbar-three-par  43%   60%    0%      7     4  contradicts the book
L9-drum-up-the-plank  80%   50%   33%      5     1  grounded and complete
L10-bicycle-wheel     83%   50%   50%      6     1  contradicts the book
L11-off-syllabus-met   -     -     -       3     3  abstained
L12-concrete-colony   67%   33%    0%     12     4  ungrounded and incomplete
------------------------------------------------------------------------------

73 claims over 11 scored turns
  groundedness   78% of claims supported (per-turn mean 79%)
  unsupported    13   contradicted 3  (in 3 of 11 turns)
  key coverage   47%   context recall 33%
  fully grounded 3/11 turns   answered with no excerpt at all: 0
  3 supported verdict(s) cite a line that is not in the excerpt -- check these by hand
  abstained off-syllabus: yes

   4  grounded and complete
   3  contradicts the book
   2  grounded but thin
   2  ungrounded and incomplete
   1  abstained
```

### 8.3 Short-set control, same corpus — 97%

```
38 claims over 12 scored turns
  groundedness   97% of claims supported (per-turn mean 98%)
  unsupported    1   contradicted 0  (in 0 of 12 turns)
  key coverage   62%   context recall 46%
  fully grounded 11/12 turns   answered with no excerpt at all: 0
  abstained off-syllabus: yes

   8  grounded and complete
   3  grounded but thin
   1  abstained
   1  right, but not from the book

JUDGE CALIBRATION  11/14 known verdicts correct (79%)
  missed real support 0%   waved a false claim through 12%
```

### 8.4 Sample turns — the question, what the model read, what it answered

Verbatim from `docs/groundedness/results/run-long-q-v1-805e1ef6.json`. Excerpt blocks are trimmed to the sentences that matter; `…` marks a trim. Questions and answers are untrimmed.

**Sample A — L8-crowbar-three-parts. The whole answer is invented, because the passage holding it was cut.**

> **Q:** My father lifted a heavy stone out of the ground in our field using a long iron rod that he rested on top of a brick near the stone. What is that kind of machine called, what are its three parts, and can you tell me what each one of those three parts actually does?

> **Read (1 passage, 592 chars, p.88):** "… All of you must have enjoyed sitting on a giant wheel. What makes the giant wheel go round ? The giant wheel is fitted to a rod at its centre. This rod is called an 'axle'. … This combination of an axle and a wheel is a simple machine. … When the pedal of a bicycle is rotated, the wheel starts rotating. How does this happen ? A wheel and axle A pulley …"

> **A:** "A fulcrum is a machine part that acts as a fulcrum, or pivot, for a lever. The fulcrum is the point around which the lever rotates. In your father's case, the fulcrum is the long iron rod that he used to lift the heavy stone. The three parts of a fulcrum machine are the fulcrum, the effort arm, and the load arm. The effort arm is the part of the fulcrum machine that the person uses to apply the force. The load arm is the part of the fulcrum machine that the load is placed on. The fulcrum machine works by applying a force to the effort arm, which causes the load arm to move, lifting the load."

What the book says (p.86, retrieved **second** and dropped by the budget, then cited to the student anyway): "Such a machine is called a lever . A lever has three parts, namely, effort, load and fulcrum." The fulcrum is the brick, not the rod. Groundedness 43%, recall 0/4 — and three of these claims were marked *supported* against the lines about axles and bicycle pedals.

**Sample B — L4-two-bar-magnets. Teaches the opposite of the book, and scores as supported.**

> **Q:** I keep two bar magnets in my school bag and something strange keeps happening with them. Sometimes when I bring them close they jump towards each other and stick, but if I turn one of them around first, they push each other away instead. What are the two ends of a magnet called, and why do these two different things happen?

> **Read (1 passage, 352 chars, p.129):** "to two ends of a bar magnet. Poles of a magnet are said to be near these ends. Try and bring a few magnets of different shapes to the classroom. Check for the location of the poles on these magnets using iron filings. Can you now mark the location of poles in the kind of magnets shown in Fig. 13.4?"

> **A:** "The two ends of a magnet are called poles. These poles are near the ends of the magnet and attract each other. When you bring two magnets close, their poles attract each other, causing them to stick together. However, if you turn one of the magnets around first, it changes the direction of the poles, causing them to push each other away instead. This is because the magnetic poles are attracted to each other, but the magnets' orientation affects how they interact with each other."

Never says north pole or south pole; never says like poles repel. Key coverage 0%, recall 0/2. The whole retrieved passage is an activity stub that cannot answer either half of the question.

**Sample C — L12-concrete-colony. The long follow-up. Topic carried correctly, second technique invented.**

> **Q (asked after "What is rainwater harvesting?" in the same session):** In my colony almost the whole ground is covered with concrete roads and cement, so where does all that rainwater even go from there, and what are the two techniques that a school building like mine could actually use to collect it?

> **Read (1 passage, 632 chars, p.144):** "One way of increasing the availability of water is to collect rainwater and store it for later use. Collecting rainwater in this way is called rainwater harvesting. The basic idea behind rainwater harvesting is "Catch water where it falls". What happens to the rainwater that falls in places that are mostly covered with concrete roads and buildings? It flows into the drains, isn't it? From there water goes to rivers or lakes, which could be far away. …"

> **A:** "Rainwater harvesting involves collecting rainwater in a way that's practical and sustainable. The basic idea is to "catch water where it falls," which means collecting rainwater where it naturally falls on rooftops, parks, and other open areas. This rainwater is then stored for later use, reducing the need to rely on distant water sources. In your colony, the rainwater that falls on the concrete roads and buildings flows into the drains and eventually to rivers or lakes. This water is then transported long distances, requiring significant effort to bring it back to homes. To address this issue, schools can implement two techniques for rainwater harvesting: **1. Rainwater Harvesting Tanks**: These are containers that collect rainwater directly from roofs. The collected water can be used for various purposes such as watering plants, cleaning, or flushing toilets. **2. Green Roofs and Rain Gardens**: These techniques involve planting vegetation on rooftops and incorporating permeable materials in the ground. This allows rainwater to seep into the soil, reducing the volume of water that needs to be transported to drains. This method can be used in both schools and residential areas."

The book's two techniques are rooftop rainwater harvesting and letting water into the ground directly from roadside drains. "Green Roofs and Rain Gardens" is the model's own. This is also the most expensive turn in the run: 266 completion tokens, 29.1 s of generation, 1,394 characters. Note the numbered headings, which the prompt forbids.

**Sample D — L11-off-syllabus-metro. Abstained on citations, answered anyway.**

> **Q:** Yesterday my uncle was telling us all about the new metro railway line that is being built in our city, and he said that the ticket prices are decided by the state government and that the coaches for it come from a big factory near Chennai. Can you explain to me how the ticket price of a metro train is actually decided, and which company makes those coaches?

> **Read:** nothing retrieved, no page cited — correct behaviour at 350 characters.

> **A:** "The metro ticket price is decided by the state government, as they set the regulations and rules for the metro system. The actual price of a ticket is determined by the fare structure, which includes factors like the distance traveled and the time of day. The coaches for the metro trains are made by a big factory near Chennai, which specializes in producing high-quality coaches for public transport systems."

It repeats the question's own premise back as established fact. The harness scores this as a pass.

**Sample E — L6-where-rain-comes-from. One of the four that worked.**

> **Q:** My little sister asked me where rain comes from, and also why the sea does not become empty even though the sun keeps drying up so much of its water every day. Can you explain the whole journey of the water to her, starting from how it goes up into the air and ending with how it comes back to the ocean?

> **Read (1 passage, 636 chars, pp.141–142):** "… water brought back to the surface of the earth by rain, hail or snow, goes back to oceans. Thus, water from the ocean and surface of the earth goes into air as vapour; returns as rain, hail or snow and finally goes back to the ocean s. The circulation of water in this manner is known as the water cycle (Fig.14.9). This circulation of water between ocean and land is a continuous process. …"

> **A:** "Sure, I'd be happy to explain the water cycle to your sister. Water evaporates from oceans, rivers, and lakes when the sun heats it up. This water vapor rises into the air, where it cools and condenses into clouds. When the clouds get heavy, they release water back to the earth as rain, snow, or hail. This water then flows back into the oceans, rivers, and lakes, completing the cycle. This continuous process keeps the water supply on land."

Key coverage 100%, groundedness 83%. This is what a compound question looks like when one passage happens to summarise the whole chapter. Note the pattern: it works because the book itself had a summary sentence, not because two passages arrived.

**Sample F — L2-tea-pan-lid. Half the question answered well, half only named.**

> **Q:** When my mother boils water in a pan for tea, the water slowly becomes less and less, and after some time I can see many small drops of water sitting under the lid. Can you tell me the names of these two processes and explain what is happening to the water in each of them?

> **Read (1 passage, 655 chars, p.41):** "… When the steam comes in contact with the metal plate cooled with ice, it condenses and forms liquid water. The water drops that you observed falling from the plate, were due to condensation of steam. The process of conversion of water vapour into its liquid form is called condensation. …"

> **A:** "When your mother boils water in a pan for tea, two processes are happening: evaporation and condensation. First, as the water heats up, it turns into steam. This steam rises and cools as it moves through the air. When it hits the lid of the pot, it cools down and turns back into water, forming the small drops you see. This process is called condensation. The water in the pot is continuously evaporating into the air, and then condensing back into water droplets when it cools down. This cycle continues until all the water has been converted into steam, and then back into water droplets."

The condensation half is grounded. The evaporation half is named but never defined, because the book's definition — "The process of conversion of water into its vapour is called evaporation" — is on p.40 and did not reach the prompt. The closing sentence is confused. Groundedness 100%, key coverage 75%: the pattern of a long question losing the half its excerpt did not cover.

---

### 9. Conclusion and next step

The hypothesis was supported, and the control run rules out the alternative explanation: the short gold set scores 97% / 62% / 46% on the same 7-book corpus that the long set scores 78% / 47% / 33% on, so question length is what moves the numbers, not the re-ingest. The mechanism is arithmetic — a 600-character passage cap under an 800-character budget means one passage reaches the prompt, and one passage cannot answer a three-part question, so the model completes the rest from its own weights in the tutor's voice. What this means for the approach as a whole is narrower than it looks: the RAG design is sound and the retrieval is mostly finding the right pages, but the two caps that were tuned for latency on short definition questions are now the binding constraint on correctness for the questions students actually ask.

- [ ]  Verdict: **adopt** the long gold set as a standing second instrument; **park** the pipeline changes it points to
- [ ]  Follow-up experiment: sweep `rag_passage_max_chars` 400 × top_k 2 against the current 600 × 1-in-practice, on both gold sets, measuring prefill tokens as well as key coverage — the cheap version of buying a second passage without raising the budget. Then, separately, re-measure `rag_exercise_page_ratio` against the NCERT books with `scripts/eval/corpus_filter_report.py`, which is what Failure 3 points at.
- [ ]  Code or docs updated: `docs/groundedness/evalset-long.json` (new gold set, 12 items) · `docs/groundedness/long-questions.md` (findings) · `docs/groundedness/results/groundedness-long-q-v1-805e1ef6.md` and `run-long-q-v1-805e1ef6.json` (long run) · `docs/groundedness/results/groundedness-short-q-control-6e57e523.md` and `run-short-q-control-6e57e523.json` (control) · no pipeline code changed
- [ ]  Shared with team on:
