# EXP-008 — One model for English + Hindi + Marathi: qwen3.5:2b and Sarvam-1 against qwen2.5:1.5b

**Approach:** English-only
**Owner:** Mayur | **Date started:** 18 Sep 2026 | **Date closed:** 24 Sep 2026 | **Status:** Failed — neither candidate replaces the incumbent
**Device tested on:** 8 GB Windows laptop (HP EliteBook 840 G8, i5-1145G7, 4 cores / 8 threads, 7.7 GiB RAM, Windows 11 Pro, CPU only, ~2.9 GiB free at launch). Tokenizer and multi-turn probes on the dev machine, marked as such.
**Related experiments:** EXP-007 (long questions) · exp005/exp006 (context-budget sweep, latency baseline) · small-model shortlist, 12 Sep (candidate funnel)

---

## 1. Context

The tutor ships split: `qwen2.5:1.5b` for English, `gemma2:2b` for Hindi/Marathi. Two payloads, two
sets of latency numbers, and a language switch the student has to get right. The question was whether
one 2B-class model could serve all three languages without losing the English latency `qwen2.5:1.5b`
was chosen for.

The binding constraint is RAM. The device has 7.7 GiB total and ~2.9 GiB free at launch, which must
hold the chat model *and* `nomic-embed-text`.

What we already knew going in, all measured:

- `qwen2.5:1.5b` spends **956 tokens per 1,000 Marathi characters** (dev machine) — Devanagari is
  effectively unaffordable on it, which is why the split build exists.
- Measured tokens per 1,000 characters, dev machine, same passages for every model:

  | | En | Hi | Mr |
  | --- | --- | --- | --- |
  | sarvam-1 | 216.5 | 274.6 | **233.1** |
  | gemma3 | 201.2 | **254.2** | 250.0 |
  | gemma2:2b | 201.2 | 352.5 | 425.7 |
  | qwen3.5:2b | 201.2 | 410.2 | 462.8 |
  | qwen2.5:1.5b | 201.2 | 932.2 | 956.1 |

  Sarvam has the best Marathi tokenizer we have measured; that is what put it on the list.
- The 11 Sep LFM2.5 test showed a model can decode faster and still lose, because its recurrent
  layers destroyed Ollama's KV-cache reuse on follow-ups.

## 2. Hypothesis

*If we replace `qwen2.5:1.5b` with a 2B multilingual model, then Hindi and Marathi become available
from a single payload while English time-to-first-word stays within +0.5 s of baseline and follow-up
cache reuse stays at or above 90%.*

The reasoning: prefill cost per token tracks decoder size on a CPU, and a 2B decoder is only ~1.5x
qwen2.5's, so the per-token penalty should be small. Both candidates tokenize Devanagari 2–4x more
cheaply than qwen2.5. The LFM2.5 result had already taught us that architecture decides the
follow-up story, so a dense-attention candidate was expected to keep its cache where a recurrent one
would not — that is the part of the hypothesis this experiment actually tested cleanly.

## 3. Why this approach over the alternatives

| Option considered | Why not chosen |
| --- | --- |
| `gemma3:4b` | Only model measured to write correct Marathi, but 3.3 GB on disk and does not fit the 2.9 GiB free at launch. Excluded on hardware, not merit. |
| `gemma3n:e2b` | 5.77 GiB resident measured — nearly 2x the available ceiling. |
| `gemma2:2b` (keep the split) | The incumbent multilingual half; this experiment exists to try to remove it, so it is the thing being replaced, not a candidate. |
| `llama3.2:3b` | Marathi probe produced a factually wrong answer about protein and water forming a shadow. Failed before latency mattered. |
| Bigger quant of either candidate | The bare `qwen3.5:2b` tag is q8_0 at 2.55 GiB and does not fit alongside the embedder. |
| Measuring on the dev Mac only | The Mac reported qwen3.5 at 74% cache reuse where the device measured 0%, and 1.48 GiB resident where the device pays ~2.5 GiB. Mac Ollama caches across runs, so `keep_alive:0` never gives a true cold reference. |
| `sarvam-1` as a shipping model | Sarvam non-commercial licence against Apache-2.0 for the qwen line; the English build is deliberately licence-clean. Measured anyway as a dense-architecture control. |

## 4. What we did — step by step

1. **18 Sep — baseline.** 50 turns of `qwen2.5:1.5b` on the device, Ollama 0.12.3, six sessions,
   800-char context budget.
2. **23 Sep — qwen3.5 arm.** Built payload `1.1.0-qwen35`. Ollama had to be bumped 0.12.3 →
   v0.32.15: the `qwen35` architecture is absent from the 0.12.3 binary (verified by string search —
   `qwen35` appears 27x in 0.32.15, 0x in 0.12.3). Backend had to send `"think": false`, or Qwen3.5
   spends the whole `num_predict` budget on a reasoning block Ollama strips, returning an empty
   answer. 11 turns.
3. **24 Sep — Sarvam build.** The published GGUF's chat template had to be replaced before it was
   worth running (§7, Failure 3):
   ```
   python3 packaging/build_payload.py --pins pins.sarvam.json --out build/payload-sarvam \
       --skip-frontend-build
   ```
   `--pins` was added for this run so the qwen3.5 build stays reproducible. Everything outside the
   `llm` section is identical between the two pins files.
4. **24 Sep — verified the payload loads from its own staged blobs** before shipping it, on a
   scratch port:
   ```
   OLLAMA_MODELS=build/payload-sarvam/runtime/models/ollama OLLAMA_HOST=127.0.0.1:11437 ollama serve
   ```
5. **24 Sep — Sarvam arm.** 12 turns on the device, same corpus and budget.

Detours that were required, not optional:

- `ollama create sarvam1-tutor:q4_K_M` wrote its manifest to `.../sarvam1-tutor/Q4_K_M`. Ollama does
  not necessarily store a tag with the case it was created with; the tag is now all-lowercase `2b`.
- `launch.ps1` hardcoded `$env:OLLAMA_MODEL`, so a variant build shipped the right blobs behind a
  launcher naming the old model. It is now stamped from pins at build time.

**Environment**

- Model / library and exact version: `qwen2.5:1.5b` (Q4_K_M) · `qwen3.5:2b-q4_K_M` ·
  `sarvam1-tutor:2b`, built from `hf.co/bartowski/sarvam-1-GGUF:Q4_K_M` with a corrected template.
  Embedder `nomic-embed-text` (768 dims) in all three arms.
- Runtime and build flags: Ollama 0.12.3 (baseline) / v0.32.15 (both candidates), vendored, CPU
  runners only — CUDA and Vulkan runners stripped from the payload. `num_ctx` 4096, temperature 0.3,
  `num_predict` 400, context budget 800 chars. AVX-512 with REPACK, flash attention on, 4 threads.
- Hardware and OS build: HP EliteBook 840 G8, i5-1145G7, 7.7 GiB RAM, Windows 11 Pro, no GPU
  backend.
- Baseline we compared against: `qwen2.5:1.5b`, 18 Sep run, same device and same 5,091-chunk corpus.

## 5. What we measured

Baseline is `qwen2.5:1.5b`. Two "after" columns because two candidates were run.

| Metric | Baseline (qwen2.5) | After: qwen3.5:2b | After: sarvam-1 | Target | Met? |
| --- | --- | --- | --- | --- | --- |
| Cold start (llama-server) | not measured | 6.29 s | not measured | — | — |
| End-to-end latency (median turn) | 8,626 ms | 13,038 ms | 8,457 ms | ≤ baseline | qwen3.5 **no** / sarvam yes |
| TTFT, new question (median) | 2,865 ms | 2,757 ms | 2,630 ms | ≤ 3,365 ms (+0.5 s) | **both yes** |
| TTFT, follow-up (median) | 1,395 ms | 3,782 ms | — | ≤ 1,895 ms | qwen3.5 **no** |
| Prefill, new question | 10.11 ms/tok | 10.18 ms/tok | 8.00 ms/tok | — | — |
| Prefill, follow-up (prefix matched) | 3.78 ms/tok | 9.43 ms/tok | 3.22 ms/tok | — | — |
| Cache reuse on follow-ups | works | **0%** | works | ≥ 90% | qwen3.5 **no** / sarvam yes |
| Decode | 16.62 tok/s | 12.21 tok/s | 11.45 tok/s | — | — |
| Output tokens / 1k answer chars | 196.7 | 191.3 | 247.3 | — | — |
| **Effective English text rate** | **84.5 chars/s** | 63.8 chars/s | **46.3 chars/s** | ≥ baseline | **both no** |
| Peak RAM (resident) | 1.3 GiB | ~2.5 GiB | not measured on device | ≤ 2.9 GiB incl. embedder | qwen3.5 tight |
| Package size (payload dir) | 1.4 GB | 2.3 GB | 2.0 GB | — | — |
| Accuracy / groundedness | not measured | not measured | not measured | — | — |

**How each number was measured.** Everything except cold start and RAM comes from
`turns-backend.csv` on the device — one row per real turn through the full RAG pipeline, not a
synthetic benchmark. n = 50 turns over six sessions (baseline), 11 turns one session (qwen3.5),
12 turns two sessions (sarvam). All figures are **medians, warm** (model already resident —
`load_ms` median 72 ms / 3 ms / 3 ms), not averaged, because the distributions are skewed by answer
length. Prefill is `prefill_ms ÷ prompt_tokens` per turn. "New question" rows are `history_msgs = 0`;
follow-up rows are `history_msgs = 1`. Effective text rate is decode ÷ tokens-per-character, which is
what the student actually perceives. Cold start and the RAM breakdown are from `ollama.err.log` for
the qwen3.5 arm only; that log was not captured for the other two runs.

**Accuracy was not measured in any arm and must not be inferred from these runs.** The qwen3.5
session logged `No Mathematics passage matched; used other subjects in grade 6` on every turn — the
questions were Maths and the corpus has no Class 6 Maths book, so the model was answering from
unrelated subjects by design.

**Tokenizer cost, measured two ways, only one of them clean.** Against **identical retrieved
context** on the device, Sarvam needs **+6.5% to +11%** more prompt tokens than qwen3.5:

| context | qwen2.5 | qwen3.5 | sarvam-1 |
| --- | --- | --- | --- |
| 389 chars | 225 tok | 232 tok | 247 tok |
| 551 chars | — | 273 tok | 303 tok |
| 610 chars | — | 272 tok | 291 tok |
| 617 chars | — | 287 tok | 308 tok |
| 815 chars | 317 tok | 326 tok | 351 tok |

The output-side figure in the table above (247.3 vs 191.3 per 1k answer chars, +29%) is **not** a
pure tokenizer measurement — the models wrote different answers, so content and style are mixed in.
Treat ~+7% as the tokenizer cost and +29% as an observed end-to-end effect.

## 6. What worked

**Running on the device rather than the dev machine.** Two of the three decisive numbers were wrong
on the Mac: cache reuse (74% Mac, 0% device) and resident size (1.48 GiB Mac, ~2.5 GiB device). The
mechanism is that Mac Ollama keeps models cached across runs, so `keep_alive:0` never produces a cold
reference to divide by, and the vision tower that inflates the device figure is only loaded by the
device's runtime path. Neither was knowable off-device.

**Splitting follow-ups by whether the prefix actually matched.** Each turn's excerpts live in the
system message, so the strict-extension cache only survives when retrieval returned the *same*
excerpts. Splitting on that converted "qwen3.5 seems not to reuse its cache" into a control:

| model | turn | ctx chars | prev ctx | same prefix? | prefill |
| --- | --- | --- | --- | --- | --- |
| qwen3.5 | fabacdf73043 | 617 | 617 | **yes** | 10.38 ms/tok |
| qwen3.5 | 4b8af6285a85 | 643 | 643 | **yes** | 9.41 ms/tok |
| qwen3.5 | 6f0cd8b4d948 | 614 | 483 | no | 9.23 ms/tok |
| qwen3.5 | 326a01a33fc5 | 643 | 614 | no | 9.45 ms/tok |
| sarvam-1 | 8c558909c91a | 610 | 610 | **yes** | **3.22 ms/tok** |
| sarvam-1 | 65e7eb05ddca | 483 | 815 | no | 7.70 ms/tok |

qwen3.5 pays a full re-prefill *even on an identical prefix*; Sarvam on an identical prefix drops to
3.22 ms/tok, matching qwen2.5's dense signature of 3.11–3.78 across 6 of its 8 follow-ups. The
mechanism is architectural: dense attention can be rewound to an earlier position, recurrent state
cannot. Caveat: n = 2 follow-ups for Sarvam, one of each kind.

**`think: false` on the device.** qwen3.5 logged `init: chat template, thinking = 0` and produced no
empty answers; Sarvam accepts and ignores the field. One backend change covered both.

## 7. What didn't work

**Failure 1 — qwen3.5 gets zero cache reuse on follow-ups**

- Symptom: follow-up TTFT 1,395 → 3,782 ms against baseline (2.7x worse); follow-up prefill
  identical to new-question prefill.
- What we tried: confirmed it is not a prompt-layout bug by holding the prefix constant (§6) — it
  re-prefills even when the previous prompt is byte-identical.
- Root cause: identified. 24 of its layers carry recurrent Gated DeltaNet state
  (`llama_memory_recurrent: 19.27 MiB, 24 layers`) that cannot be rewound; only 6 are true attention
  (`full_attention_interval = 4`), which is also why its KV cache is only 48 MiB at 4096.
- Dead end. Not tunable and not a packaging mistake. The strict-extension prompt layout and the whole
  follow-up latency story are worth nothing on this architecture.

**Failure 2 — Sarvam-1 loses the conversation on turn 2**

- Symptom (dev machine): T1 "What is a shadow?" answered correctly. T2 "Why does it move when I
  move?" answered about **proprioception** and hand movement. T3 "Can you give me one example?"
  invented a **"Rule of Four" in the game of Go**.
- What we tried: three message formats — the stock ChatML template, `### Question:/### Answer:`
  headings, and a `Student:/Tutor:` dialogue frame. All three failed identically, with different
  confabulated subject matter (viscoelasticity and the pressure-gradient force; telephone networks
  and air traffic control).
- Root cause: identified as the model, not the format. Prompt tokens climbed 98 → 130 → 267 across
  the three turns, which proves the history *was* being rendered — the model does not carry it.
- Dead end for this product. The follow-up carrying that took the tutor from 4/10 to 7/10 is inert
  on it. On device this shows as a median answer of 319 chars against qwen3.5's 596, with two stub
  answers of 53 and 73 characters.

**Failure 3 — Sarvam's published GGUF ships an unusable chat template**

- Symptom: answers ended with a visible ` </s>` leaked into the message body.
- What we tried: measured whether the template's markers exist in the model's vocabulary, using
  `raw: true` prompts against a 1-character control to cancel the BOS token.
- Root cause: identified. `hf.co/bartowski/sarvam-1-GGUF:Q4_K_M` declares ChatML markers that are
  absent from its 68,096-token Indic vocabulary — `<|im_start|>` and `<|im_end|>` split into **5**
  literal pieces each, while `</s>` and `<s>` are single real tokens. So ~10 junk tokens are spent
  per turn and both `stop` parameters are unreachable; generation ends only on the model's own EOS.
- Parked, then fixed: `packaging/ollama/sarvam1-tutor.Modelfile` supplies a `.Messages`-aware
  template stopping on the real `</s>`. The fix also flipped the Marathi shadow answer from wrong
  (*refraction* forms the shadow) to correct (the object blocks the light). Hindi stayed wrong in
  both (says light is *reflected* onto the screen).

**Failure 4 — neither candidate delivers the multilingual goal regardless of latency**

- Symptom: Hindi and Marathi questions retrieve poorly in both arms.
- Root cause: identified, and it is not the chat model. `nomic-embed-text` does not embed Devanagari
  usefully, so retrieval is English-only whichever model generates.
- Parked. Fixing it means a multilingual embedder, new dimensions, task prefixes in
  `rag/embeddings.py`, and a full corpus re-ingest.

## 8. Error logs

qwen3.5, on **every one of the 11 turns** (trimmed to the three relevant lines; the block repeats
per turn):

```
forcing full prompt re-processing due to lack of cache data
(likely due to SWA or hybrid/recurrent memory, see llama.cpp#13194)
erased invalidated context checkpoint (pos_min = 240, pos_max = 240, n_tokens = 241 ...)
```

The clearest single case — llama-server measured the new prompt as 95.1% identical to the previous
one, selected that cache slot, then discarded it and re-prefilled all 245 tokens:

```
sim = 0.951 (233/245)
llama_memory_recurrent: 19.27 MiB, 24 layers
```

Sarvam vocabulary probe, dev machine, Ollama 0.32.15 (full output, untrimmed):

```
control 'x' = 2 tok  (BOS overhead = 1)
'<|im_start|>'     ->  5 extra tok   split into pieces (NOT in vocab)
'<|im_end|>'       ->  5 extra tok   split into pieces (NOT in vocab)
'</s>'             ->  1 extra tok   SINGLE TOKEN (in vocab)
'<s>'              ->  1 extra tok   SINGLE TOKEN (in vocab)
'<|endoftext|>'    ->  5 extra tok   split into pieces (NOT in vocab)
```

Build failure caught by the new staging assertion, before the payload shipped (trimmed of progress
bars):

```
    creating sarvam1-tutor:q4_K_M from sarvam1-tutor.Modelfile
chat_model 'sarvam1-tutor:q4_K_M' is not among the staged manifests.
  Staged: ['hf.co/bartowski/sarvam-1-GGUF/Q4_K_M',
           'registry.ollama.ai/library/nomic-embed-text/latest',
           'registry.ollama.ai/library/sarvam1-tutor/Q4_K_M']
```

### 9. Conclusion and next step

The hypothesis is not supported. Neither candidate keeps English latency: qwen3.5 loses cache reuse
entirely and runs the median turn 51% longer, and Sarvam — despite the best prefill and TTFT of the
three — produces English text 45% slower than the incumbent because per-token wins are cancelled by
needing more tokens. Neither delivers multilingual either, since retrieval is English-only in both.
The multilingual goal is blocked on RAM, not on model choice: every model measured to write correct
Marathi is Gemma-3-generation at ≥4B effective parameters and none fits in 2.9 GiB.

- [ ]  Verdict: **reject both candidates.** `qwen2.5:1.5b` stays; the split build stays.
- [ ]  Follow-up experiment: fit a 16 GB SODIMM (the 840 G8 has two user-accessible slots) and re-run
  this comparison with `gemma3:4b` and `gemma3n:e2b` included. Separately, move retrieval to a
  multilingual embedder before any Hindi/Marathi claim is made.
- [ ]  Code or docs updated: `packaging/build_payload.py` (`--pins`, derived-tag support, launcher
  model stamped from pins), `packaging/pins.sarvam.json`, `packaging/ollama/sarvam1-tutor.Modelfile`,
  this document.
- [ ]  Shared with team on:

**Open question on the Sarvam arm.** The turn log does not record a model name. The run is attributed
to Sarvam from its tokenizer signature (247.3 vs 191.3 output tokens per 1k answer chars), which is
unambiguous on the same device and corpus, but it is not known whether it used `sarvam1-tutor:2b` or
the stock tag. If it was the stock tag, its prompt-token counts are inflated by roughly 10 tokens per
turn. Confirm from `$env:OLLAMA_MODEL` or `ollama.err.log` before these numbers leave this document.
