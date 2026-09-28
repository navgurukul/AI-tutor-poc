# Why groundedness is 84% and key coverage 75% — causes, with evidence

**Source run:** `results/run-qwen35-multibook-ff83c4f2.json` and
`results/groundedness-qwen35-multibook-109b72c3.md` — qwen3.5:2b-q4_K_M, 14 items over 6 NCERT
books, judge gemma3:4b, 28 Sep 2026.
**Method:** re-read every turn's retrieved sources, the excerpt block actually sent to the model, and
each judged claim; then re-ran real retrieval at `k=80` to find where each gold chunk ranked.
**No code was changed.** Every number below is measured from the run or from read-only retrieval
against the same corpus, and simulated figures are labelled as such.

---

## 1. The dominant cause: the budget throws away a passage it already paid to retrieve

`within_budget` (`app/services/rag/retrieval.py`) packs passages **all-or-nothing**: if the next
passage does not fit whole, it `break`s. It never truncates the second passage to the room left.

Measured across the 14 turns:

| | |
| --- | --- |
| Cited sources that never reached the prompt | **13 of 28 (46%)** |
| Turns that lost their second passage | **13 of 14** |
| Unused budget on those turns | median **203 chars**, max **451** (of 800) |
| Combined length both passages needed | median ~1,137 chars (simulated) |

So on a typical turn the model read ~600 characters, ~200 characters of budget sat unused, and a
passage the retriever had already ranked and cited was discarded whole. The citation is still shown
to the student, because citations are built from the untrimmed hits — the student is told the tutor
read a page it never saw.

**This is the direct cause of three of the four zero-recall turns.** Re-running retrieval shows the
gold chunk ranked *inside* `rag_top_k=2` for M2-herbivores, M3-nutrients and M11-displacement — it
was retrieved, then dropped by the packer:

| item | gold rank | gold distance | what happened |
| --- | --- | --- | --- |
| M2-herbivores | 2 | 0.2539 | retrieved, cut by budget |
| M3-nutrients | 2 | 0.2511 | retrieved, cut by budget |
| M11-displacement | 2 | 0.2482 | retrieved, cut by budget |
| M7-density | 4 | 0.3268 | `top_k=2` too small — distance would have passed the 0.42 gate |

Only M7 is a genuine ranking failure. The docstring already records this failure mode from exp004
(9 of 20 turns); on the 7-book corpus it has got worse, not better.

## 2. What the model reads instead: chapter-end summary pages

When the teaching passage is cut, what survives is often the chapter recap. **3 of the 15 passages
actually read were bullet-list summary pages.** M11 is the worst case and explains its invented
chemistry completely. The entire excerpt it was given was:

```
[1] NCERT Class 10 Science - Rancidity - p. 14
/square6Reactions in which energy is absorbed are known as endothermic reactions.
/square6When an element displaces another element from its compound, a displacement reaction occurs.
/square6Two different atoms or groups of atoms (ions) are exchanged in double displacement reactions.
...
2. Fe2O3 + 2Al → Al2O3 + 2Fe
```

A one-line definition, an unrelated neighbouring definition, and a bare equation with no working.
The p.11 passage holding the iron/copper-sulphate example was cited and cut. Note also the heading
is `Rancidity` — wrong for this content, which is the inert header detector already logged in
`ingestion-gaps-2026-09-21`.

## 3. The style rule mandates two sentences the excerpt usually cannot support

The socratic rule requires the model to "explain **how or why it happens**", then "give one
**everyday example** a student can picture". A definition-only excerpt contains neither. The model
cannot comply and stay grounded, so it invents — and the invention is confident:

| item | mandated part | what it invented |
| --- | --- | --- |
| M11 | how/why | "elements naturally want to form their own stable compounds" — **contradicted** |
| M11 | example | iron + copper sulphate → "iron oxide"; baking soda + vinegar as displacement |
| M9 | how/why | "reactants merge into one unified substance without breaking down beforehand" |
| M4 | how/why | "grown on a large scale in a single place **for many years at once**"; a false etymology |
| M2 | example | ecosystem commentary — "predict how ecosystems balance out over time" |

The harness already excludes the closing invitation from scoring, because mandating it would put a
floor under every score. The mechanism and example sentences are mandated in exactly the same way
and are *not* excluded — they are scored as claims, and they are where most unsupported claims come
from.

## 4. The judge undercounts the real error rate

Calibration: 86% correct, **missed real support 0%**, **waved a false claim through 22%**. It is
credulous, not strict — it fails only in the direction that inflates the score. Two examples from
M11 that it marked **supported**:

- "the iron will push out the copper … and create new substances like **iron oxide** and metallic
  copper" — it produces iron sulphate. Judge cited the generic definition line as support.
- "aluminum displaces **oxygen** from iron oxide" — aluminium displaces *iron*. Judge cited the bare
  equation `Fe2O3 + 2Al → Al2O3 + 2Fe` as support.

So M11's real score is worse than the 1 contradiction recorded, and **84% is an upper bound on a
number that is itself being graded by an instrument with a known 22% false-pass rate.**

---

## 5. Key coverage: three of the five misses are my eval set's fault, not the model's

`required_facts` matches literal substrings. Inserted adjectives break it:

| item | key phrase looked for | what the answer actually said | verdict |
| --- | --- | --- | --- |
| M1-ant-smell | `leaves a smell` | "it leaves a **faint** smell on the ground" | **false negative** |
| M2-herbivores | `eat other animals` | "carnivores are animals that eat other **living** animals" | **false negative** |
| M9-combination | `single product` | "join together to create a single **new** product" | **false negative** |
| M4-crop | `same kind` / `same type` | never says it — defines a crop without its distinguishing clause | **real miss** |
| M13-crop-classified | `season` | classifies by region and "local weather conditions" | **real miss** |

So **key coverage is understated: 75% measured, ~89% on substance** (11 of 12 scorable facts once
the three phrasing artefacts are discounted). The repo's own harness docstring already warns about
this class (`"in contact" could never match "come into contact"`); the multi-book set reproduced it.

The two real misses have different causes:

- **M4** genuinely dropped the defining clause and padded with invention. A generation failure.
- **M13** answered "classified by region" because the passage naming the *seasons* was the one the
  budget cut. A retrieval-delivery failure wearing a key-coverage mask.

---

## 6. What to change, ranked by evidence per unit of effort

**1. Pack the budget partially instead of all-or-nothing.** Fit as many sentences of passage 2 as
the remaining room allows, rather than dropping it whole. `shorten()` already selects sentences, so
the machinery exists. Measured upside: reclaims a median 203 unused characters on 13 of 14 turns and
would have delivered the gold passage for M2, M3 and M11 — three of the four zero-recall turns.
**Cost: zero.** The budget, and therefore prefill time, does not change. This is the single highest
-value change on the page.

**2. Stop citing passages the model never read.** A source that the packer dropped should not appear
in the student's citation list. 13 of 28 citations in this run were unread. This is a trust bug
independent of accuracy, and it makes every manual audit misleading.

**3. Raise `rag_context_max_chars` from 800 towards ~1,150.** Simulated median combined length is
1,137. Cost on the target laptop at ~10.2 ms per prompt token: roughly +85 tokens ≈ **+0.9 s TTFT**.
Worth measuring against (1), which is free — do (1) first and re-measure before paying this.
Note exp006 chose 800 on the *single-book* corpus with qwen2.5; the 7-book corpus has different
chunk lengths and that result should not be assumed to carry over.

**4. Raise `rag_top_k` from 2 to 3–4.** Only helps M7 (gold at rank 4, distance 0.3268, comfortably
inside the 0.42 gate) — one turn in fourteen. Pointless before (1), because a third passage will be
dropped by the same packer. Do it after.

**5. Let the model say the book does not say.** The style rule's mandated mechanism and example are
the origin of most invented claims. Permitting "the book doesn't explain why" would remove the
pressure that produced M11's chemistry. This needs an A/B — it will shorten answers and may trade
key coverage for groundedness.

**6. Down-rank chapter-end summary pages.** They outranked teaching pages and carry definitions with
no working. Needs an ingestion-side label; related to the inert header detector already logged.

**7. Before trusting any of these numbers, harden the judge.** A 22% false-pass rate on polarity
flips is large enough to hide a regression. Until it is fixed, treat groundedness as directional.
`gemma3:4b` was chosen for being larger than the 1.5B under test; against a 2B it is no longer
comfortably larger.

**8. Replace literal `required_facts` matching with the judge**, or at minimum tolerate inserted
modifiers. Three of five key-coverage misses in this run were phrasing artefacts.

---

## 7. What this run does *not* show

- **It does not show that retrieval ranking is broken.** 13 of 14 gold chunks ranked within the top
  2 of their grade partition. The embedder did its job; delivery to the prompt is what failed.
- **It does not show the model is well grounded.** The judge's 22% false-pass rate means the true
  error count is higher than 4 contradictions, demonstrated on M11.
- **It does not compare models.** One model, one run, no interleaving. qwen2.5:1.5b has not been run
  on this multi-book set, so the 84% has no baseline beside it.

---

## 8. What happened when three of these were applied — four arms, 28 Sep

Applied: (1) partial packing with overlap dedupe, (2) citations built from the passages read, and
(3) permission to say the book does not explain something. Same eval set, model and judge each time.

| arm | groundedness | unsupported | contradicted | key coverage | context recall |
| --- | --- | --- | --- | --- | --- |
| before | 84% | 8 | 4 (3 turns) | 75% | 68% |
| (1)+(2) only | 86% | 7 | 3 (3 turns) | 68% | **80%** |
| (1)+(2)+(3) first wording | 88% | 5 | 4 (4 turns) | 75% | **80%** |
| (1)+(2)+(3) second wording | 88% | 7 | 2 (2 turns) | **57%** | **80%** |

**Read the generation columns with suspicion. There is no seed anywhere** — not in the backend, the
Ollama client or the harness — and sampling runs at temperature 0.3. With 14 items and ~12 scorable
key facts, one fact moves key coverage about 8 points and one claim moves groundedness about 1.5.
The 57-75% spread in key coverage is roughly two facts. **Every generation-quality difference in
that table is inside the noise of a single run.**

What is outside it, because it does not depend on sampling:

- **Context recall 68% -> 80%**, identical across all three post-fix arms. Retrieval, packing and
  dedupe are deterministic. This is fix (1) working.
- **M11-displacement reads the p.11 teaching passage instead of the chapter-end summary bullet**,
  0% -> 100% recall. The specific failure this analysis was written about is gone.
- **Citations: 13 of 28 unread -> 0**, by construction. Fix (2) is structural.

### Fix (3) does not work as written and should probably be reverted

It fired on 6-7 of 14 turns in both wordings, and in both it produced fourth-wall breaks and
deflection rather than honest gaps:

- "Students should remember that the book does not explain how or why this energy transfer occurs"
  — the instruction restated at the student. Present in BOTH wordings.
- "According to the textbook excerpt, reactions that release heat..." — names the plumbing.
- "please check your textbook for additional details on their specific behaviors" (M1) and "Please
  try reading your textbook examples again" (M12) — deflects the question back to the student.

It also costs content. Under the second wording M10 stopped saying heat is released and M11 stopped
saying one element displaces another — the definitions themselves, crowded out of the ~100-word
budget by the gap sentence. One legitimate use appeared: "the book does not explain how an ant knows
which smell belongs to its own path", which is exactly the intent. One win against two failure modes
is not a good trade, and the file's own comments predicted the echo ("naming them also gets them
echoed").

**Before this is judged again, set a seed.** Until generation is reproducible, a 14-item run cannot
resolve a change this size, and every arm above except context recall is a coin flip dressed as a
measurement.

---

## 9. Where it landed: fix (3) reverted, budget raised to 1000

Fix (3) was reverted for the reasons in section 8. `rag_context_max_chars` went 800 -> 1000, which
is only worth doing *because* the packer now cuts rather than drops -- extra budget buys sentences
instead of all-or-nothing passages.

| arm | groundedness | unsupported | contradicted | key coverage | context recall |
| --- | --- | --- | --- | --- | --- |
| before | 84% | 8 | 4 | 75% | 68% |
| packing + dedupe, 800 | 86% | 7 | 3 | 68% | 80% |
| **packing + dedupe, 1000** | **84%** | **9** | **3** | **79%** | **89%** |

**Context recall 68% -> 89%.** This is the deterministic half of the table and the part worth
believing. What remains is exactly the two things predicted: M7-density, whose gold ranks 4 and so
needs `rag_top_k` raised from 2 (a budget cannot reach it), and one of M13's two quotes.

**Groundedness did not move: 84% before, 84% after.** Claims rose from 74 to 76 and unsupported from
8 to 9, so the ratio held while the model was given more to read. That is the useful finding here:

> The bottleneck has moved. It was "the model never saw the answer" -- 4 turns with zero recall, and
> the worst of them inventing chemistry. It is now "the model says more than it saw". Retrieval
> delivery is close to solved; groundedness is limited by generation.

Two consequences:

1. **More context is not the lever for groundedness any more.** The remaining unsupported claims are
   the mandated "how or why" sentence and the mandated everyday example, which extra passages do not
   supply. That pressure is real and fix (3) was the right instinct aimed badly -- it has to land in
   the answer's own voice.
2. **The judge is now the binding constraint on measurement.** At a 22% false-pass rate on polarity
   flips it cannot resolve the differences left in this table, and it credited two wrong chemistry
   claims in the original run. Fix the instrument before tuning against it.

Still open, in order: raise `rag_top_k` to 3-4 (closes M7, now that a third passage will be cut to
fit rather than dropped); set a generation seed so a 14-item run means something; harden the judge;
replace literal `required_facts` matching.
