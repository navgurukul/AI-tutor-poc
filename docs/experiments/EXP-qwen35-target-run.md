# Qwen3.5-2B on the target laptop — measured run, 23 Sep 2026

**Status:** measurements only. Held for the report that compares this against Sarvam-2B on the same device.
**Device:** HP EliteBook 840 G8, i5-1145G7 (4 cores / 8 threads, AVX-512 + VBMI + VNNI), 7.7 GiB RAM, Windows 11, CPU only.
**Build:** payload 1.1.0-qwen35 — `qwen3.5:2b-q4_K_M` + `nomic-embed-text`, vendored Ollama v0.32.15, `think:false`, num_ctx 4096, temp 0.3, context budget 800.
**Baseline:** `qwen2.5:1.5b` on Ollama v0.12.3, 18 Sep run, same device and corpus.
**Source logs:** `Target HP data/logs/` (backend.err, ollama.err, turns-backend.csv), session `cc4e4aeea700`, 16:24–16:35 IST.

## 1. Headline

| | qwen2.5:1.5b (18 Sep) | qwen3.5:2b-q4_K_M (23 Sep) |
| --- | --- | --- |
| Prefill, new question | 10.19 ms/token | **10.18 ms/token** |
| Prefill, follow-up | 3.78 ms/token | **9.43 ms/token** |
| TTFT, new question (median) | 3,025 ms | **2,757 ms** |
| TTFT, follow-up (median) | 1,395 ms | **3,782 ms (2.7x worse)** |
| Decode | 16.6 tok/s | **12.2 tok/s (-27%)** |
| Total turn (median) | 7,817 ms | 13,038 ms |
| Answer length (median) | 438 chars | 596 chars |
| **Per answer character** | **15.6 ms** | **20.5 ms (+31%)** |
| n | 14 turns | 11 turns |

Per *uncached* prompt token the two models are identical on this CPU — 10.19 vs 10.18 ms. Every
difference below comes from the cache and from decode, not from prefill cost per token.

## 2. The finding: cache reuse is zero, and it is architectural

`llama-server` re-processed the entire prompt on **every one of the 11 turns**:

```
forcing full prompt re-processing due to lack of cache data
(likely due to SWA or hybrid/recurrent memory, see llama.cpp#13194)
erased invalidated context checkpoint (pos_min = 240, pos_max = 240, n_tokens = 241 ...)
```

The clearest case is task 1018: llama-server measured the new prompt as **95.1% identical to the
previous one** (`sim = 0.951 (233/245)`), selected that slot, and then threw the state away and
re-prefilled all 245 tokens. A checkpoint is written after every turn (19.27 MiB each, 5 prompts /
218 MiB cached by the end) and invalidated before every next turn.

This is the LFM2.5 failure mode, reproduced exactly: 24 of Qwen3.5-2B's layers carry recurrent
Gated DeltaNet state (`llama_memory_recurrent: 19.27 MiB, 24 layers`) that cannot be rewound to an
earlier position, so no prefix can be reused. Only 6 layers are true attention
(`full_attention_interval = 4`), which is also why its KV cache is tiny — 48 MiB at 4096 tokens.

**Consequence for the product:** the strict-extension prompt layout, the excerpts-at-the-front rule
and the whole follow-up latency story are worth nothing on this architecture. Follow-ups cost the
same as new questions. This is not tunable and not a packaging mistake.

## 3. Memory

| | |
| --- | --- |
| Free RAM at llama-server start | 1,666 MiB (embedder), 1,413 MiB (chat model) |
| Text weights | 522.99 MiB + 652.01 MiB CPU_REPACK = 1,175 MiB |
| KV cache (4096, 6 attention layers) | 48 MiB |
| Recurrent state (24 layers) | 19.27 MiB |
| Compute buffer | 52 MiB |
| **Vision tower (mmproj)** | **957.74 MiB worst case, 1,945 MiB model size** |

**The vision encoder is loaded even though the tutor is text-only.** Ollama passes the same blob as
`--mmproj` and llama.cpp translates it (`handle_qwen35_like_clip: detected Ollama-format qwen35 GGUF
used as mmproj`). That is ~1 GB of an 7.7 GiB machine spent on a CLIP tower that never sees an image.
This corrects the 1.48 GiB resident figure measured on the dev Mac — the device pays more.
Worth testing whether a text-only GGUF (no mmproj) recovers it.

## 4. Other facts worth keeping

- `think:false` works on the device: `init: chat template, thinking = 0`. No empty answers occurred.
- Ollama's built-in `qwen3.5` renderer is used (`selected=renderer_parser renderer=qwen3.5`), not a
  Go template — so the qwen3-style template fix is not available on this model.
- Its sampler defaults are unusual and were not chosen by us: **presence_penalty 1.5**, top_k 20,
  top_p 0.95. Worth an A/B before blaming the model for anything.
- `llama-server` cold start: 6.29 s for the chat model, 2.52 s for the embedder.
- The CPU path selected AVX-512 with REPACK and flash attention on, 4 threads.
- `OLLAMA_VULKAN:true` is in the server config, but no Vulkan runner ships, so it fell back to CPU.
  The deliberate strip worked as intended.
- The embedder is requested at num_ctx 8192 but `n_ctx_train = 2048` — warned on every load.
  Pre-existing, unrelated to this model.

## 5. Caveats — read before quoting any of this

- **Groundedness from this session is not interpretable.** Every turn logged
  `No Mathematics passage matched; used other subjects in grade 6` — the questions were Maths and the
  corpus has no Class 6 Maths book. The model was answering from unrelated subjects by design.
- n = 11 turns, one session, one sitting. The 18 Sep baseline is n = 14 across six sessions.
- Answer lengths differ (596 vs 438 chars median), so compare the per-character figure, not totals.
- Hindi/Marathi were not exercised on the device. Dev-machine probes found the Marathi wrong
  (see [[multilang-single-model]]); retrieval is English-only here regardless.

## 6. For the Sarvam-2B comparison

To be a fair A/B, the Sarvam run needs: the same device, the same corpus and budget, novel questions
per arm, interleaved order, and **questions whose subject is actually in the corpus**. Record the same
six numbers as §1, plus the cache-reuse line from `ollama.err.log` — for a dense model it should show
prefix reuse rather than `forcing full prompt re-processing`, and that single line is the largest
latency difference between the two candidates.

---

# Sarvam-1 (2B) — paper check, 24 Sep 2026

Checked before spending a target run. **Two blockers make the target run pointless as a product
candidate**; the measurements below are kept because they calibrate the others.

| Blocker | Evidence |
| --- | --- |
| Not a chat model | Model card: *"This is a text-completion model... cannot be used directly as a chat or an instruction-following model."* No instruct variant exists at this size — HF has sarvam-1, sarvam-1-v0.5, sarvam-2b-v0.5 (all base), then jumps to sarvam-30b / 105b. |
| Non-commercial licence | `LICENSE.md` = "Sarvam non-commercial license"; no `license:` tag declared on the repo. The English build is deliberately Apache-2.0-clean. |

Demonstrated: given the tutor system prompt and "सावली कशी तयार होते?", it answered
*"सावली हा एक प्रकारचा कापड आहे..."* ("Savali is a type of fabric made from silk and wool") and
leaked `</s>` into the message body — an encyclopedic completion, not a tutor answer. No excerpts
were supplied in that probe, so it shows instruction-following failure, not grounding failure.
Its Marathi prose is **grammatically clean** — visibly better than gemma2:2b or qwen3.5 produced.
The language ability is real; the instruction tuning is what is missing.

## Measured (dev Mac, same passages and method as every other model)

| tokenizer | En | Hi | Mr | Mr tok/word |
| --- | --- | --- | --- | --- |
| **Sarvam-1** | 216.5 | 274.6 | **233.1** | **1.50** |
| Gemma 3 / 3n / 4 | 201.2 | **254.2** | 250.0 | 1.61 |
| gemma2 | 201.2 | 352.5 | 425.7 | 2.74 |
| qwen3.5 | 201.2 | 410.2 | 462.8 | 2.98 |
| qwen2.5 / qwen3 | 201.2 | 932.2 | 956.1 | 6.15 |

**Sarvam has the best Marathi tokenizer measured** — 7% ahead of Gemma 3, 2x qwen3.5, 4x qwen2.5.
It is marginally behind Gemma 3 on Hindi and 8% behind on English.
Resident **1.96 GiB** at num_ctx 4096 (`ollama ps`, `hf.co/bartowski/sarvam-1-GGUF:Q4_K_M`, 1.5 GB file).

## Projected on target (from config.json, not run)

28 layers, hidden 2048, intermediate 11008, 16 heads / 8 KV heads, vocab 68,096, untied embeddings
-> **2.25B decoder params**, 1.7x qwen2.5's 1.31B.

| | qwen2.5:1.5b (measured) | qwen3.5:2b (measured) | Sarvam-1 (projected) |
| --- | --- | --- | --- |
| Architecture | dense | recurrent | **dense (llama)** |
| Cache reuse | works | **zero** | should work |
| Prefill | 10.19 ms/tok | 10.18 ms/tok | ~17.4 ms/tok |
| Decode | 16.6 tok/s | 12.2 tok/s | ~10.7 tok/s |
| KV @ 4096 | 112 MiB | 48 MiB | ~458 MiB |
| Resident | 1.3 GiB | ~2.5 GiB (incl. ~1 GB vision) | **1.96 GiB (measured)** |
| Loads on 0.12.3 | yes | **no** | **yes** |
| Licence | Apache-2.0 | Apache-2.0 | **non-commercial** |

Its one decisive advantage over qwen3.5 is being dense: the strict-extension cache would work, so
follow-ups would stay fast instead of costing a full re-prefill (1,395 ms -> 3,782 ms on this device).
It also needs no runtime bump. Against that: 1.7x the prefill compute, ~12% slower decode, and a KV
cache 4x qwen2.5's because all 28 layers are real attention.

**Recommendation: do not spend a target run on it as a product candidate.** If a run happens anyway,
it is only useful as a tokenizer-and-fluency calibration point for the Gemma comparison.

---

## Sarvam-1 build, 24 Sep 2026

Built anyway on request, as `build/payload-sarvam` from `packaging/pins.sarvam.json`. Everything
except the `llm` section is byte-identical to the qwen3.5 pins -- same Ollama v0.32.15, same corpus,
same frontend -- so the target run is a clean A/B and nothing but the model varies.

### The published GGUF ships the wrong chat template

`hf.co/bartowski/sarvam-1-GGUF:Q4_K_M` declares a ChatML template and ChatML stop strings. Sarvam-1
is a Llama-architecture base model whose 68,096-token Indic vocabulary does not contain those
markers. Measured on Ollama 0.32.15 with `raw:true` prompts against a 1-char control to cancel BOS:

| string | extra tokens | in vocab? |
| --- | --- | --- |
| `<\|im_start\|>` | 5 | no -- splits into literal pieces |
| `<\|im_end\|>` | 5 | no -- splits into literal pieces |
| `<\|endoftext\|>` | 5 | no |
| `</s>` | 1 | **yes** |
| `<s>` | 1 | **yes** |

So the stock tag burns ~10 tokens per turn on markers the model has never seen, and both its `stop`
parameters are unreachable -- generation ends only on the model's own EOS, which then leaks into the
answer as a visible ` </s>`. `packaging/ollama/sarvam1-tutor.Modelfile` replaces the template with a
`.Messages`-aware one using plain ASCII headings and stops on the real `</s>`. Single-turn effect,
same seed and prompt:

| | stock tag | corrected tag |
| --- | --- | --- |
| English | correct, trailing ` </s>` | correct, clean |
| Hindi | **wrong** (light is "reflected" onto the screen) | **wrong**, identical error |
| Marathi | **wrong** ("refraction" forms the shadow) | **correct** (object blocks the light) |

### Multi-turn is broken, and it is the model, not the template

Three message-format variants were tried: stock ChatML, `### Question:/### Answer:` headings, and a
`Student:/Tutor:` dialogue frame. All three behave identically -- T1 is fine, and then:

| turn | prompt tok | result (corrected tag) |
| --- | --- | --- |
| T1 "What is a shadow?" | 98 | correct and terse |
| T2 "Why does it move when I move?" | 130 | topic lost -- answers about **proprioception** and hand movement, runs to the token cap |
| T3 "Can you give me one example?" | 267 | confabulation -- invents a **"Rule of Four" in the game of Go** |

The other two variants fail the same way with different subject matter (viscoelasticity, the
pressure-gradient force; telephone networks, air traffic control). The prompt token counts climb
98 -> 130 -> 267, which proves the template *is* rendering the history -- the model simply does not
carry it. This is the model card's "cannot be used directly as a chat or an instruction-following
model" showing up exactly where this product needs it most: the follow-up carrying work that took
the tutor from 4/10 to 7/10 is inert on this model.

`think:false` is accepted and ignored -- no backend change needed.

### Cache reuse: Mac numbers contradict the target, which is why the run is needed

| | Mac, Ollama 0.32.15 | Target, Ollama 0.32.15 |
| --- | --- | --- |
| qwen3.5:2b-q4_K_M | 74.0% | **0%** (measured) |
| sarvam1-tutor:2b | 66.6% | not yet measured |

Both Mac figures are directional only -- Mac Ollama caches across runs, so `keep_alive:0` never gives
a true cold reference. The qwen3.5 row disagreeing with its own target measurement is the point: the
Mac cannot settle this, and Sarvam being dense is a prediction the target run would confirm or kill.

### What the target run can and cannot answer

Worth measuring: prefill and decode on the real CPU, resident RAM (~1.96 GiB leaves ~0.5 GiB more
headroom than qwen3.5), Devanagari tokenizer throughput, and whether dense attention restores cache
reuse.

Not worth measuring: anything multi-turn, and anything about answer quality beyond single-turn
recall. The non-commercial licence still closes it as a product candidate regardless of result.

### Payload verified on the build machine

`build/payload-sarvam`, 4183 files / 2013 MB, payload_version `1.2.0-sarvam1`. Served straight from
the payload's own staged blobs on a scratch port, the packaged tag loads and answers:

```
sarvam1-tutor:2b   8b537cbd86d7   2.1 GB   100% CPU   ctx 4096
"What is a shadow?" -> "A shadow is formed when an opaque object blocks light."   done_reason: stop
```

2.1 GB resident plus nomic-embed-text (~0.35 GiB) is ~2.3 GiB against the 2.9 GiB the target has free
at launch -- roughly 0.6 GiB more headroom than the qwen3.5 payload. Checks that caught the three
previous packaging bugs all pass: packaged `ollama.exe` reports 0.32.15 (not a stale cached 0.12.3),
`lib/ollama/llama-server.exe` is present, `runtime/python/python.exe` is present, `textbook_ingest`
installed non-editable with no `__editable__*` or `.pth` leak, and the launcher's `OLLAMA_MODEL` is
stamped `sarvam1-tutor:2b` from pins rather than hardcoded.

One build-script bug was found and fixed in the process: Ollama does not necessarily store a tag with
the case it was created with -- `ollama create sarvam1-tutor:q4_K_M` wrote its manifest to
`.../sarvam1-tutor/Q4_K_M`, and the new staging assertion (correctly) rejected the build. The tag is
now all-lowercase `2b` and the assertion compares case-insensitively.

---

## Sarvam-1 on target, 24 Sep 2026 — 12 turns

Source: `turns-backend.csv`, session `251faa713d1d4d5685d0d205653e40d2` (11 turns) plus
`d2497a474d814bbc90f97336e81e6a83` (1 turn), 10:16-10:25 UTC. The turn log does not record the model
name; this is attributed to Sarvam from its tokenizer signature (below), which is unmistakable
against the 23 Sep qwen3.5 rows on the same device, same corpus, same questions.

### Headline: the prediction was right, the projection was wrong, and the tokenizer story reverses

| | qwen2.5:1.5b (18 Sep) | qwen3.5:2b (23 Sep) | **Sarvam-1 (24 Sep)** |
| --- | --- | --- | --- |
| n turns | 50 | 11 | 12 |
| Prefill, fresh question | 10.11 ms/tok | 10.18 ms/tok | **8.00 ms/tok** |
| Decode | 16.62 tok/s | 12.21 tok/s | 11.45 tok/s |
| Median TTFT | 2865 ms | 2757 ms | 2630 ms |
| Output tokens / 1k answer chars | 196.7 | 191.3 | **247.3** |
| **Effective text rate** | **84.5 chars/s** | **63.8 chars/s** | **46.3 chars/s** |
| Median answer length | -- | 596 chars | 319 chars (2 stubs < 150) |

Two of my earlier projections were wrong and are corrected here: prefill was projected at
~17.4 ms/tok and measured **8.00** -- 2.2x too pessimistic, and actually *faster per token* than
either qwen model. Decode was projected ~10.7 tok/s and measured 11.45, close enough.

**The finding that matters is the last row.** Sarvam's much-praised Indic tokenizer is a Marathi
advantage only. On English it is 29% *worse* than qwen3.5 -- confirmed on identical retrieved
context, where it needs 6-11% more prompt tokens for the same excerpts:

| context | qwen2.5 | qwen3.5 | Sarvam |
| --- | --- | --- | --- |
| 389 chars | 225 tok | 232 tok | 247 tok |
| 551 chars | -- | 273 tok | 303 tok |
| 610 chars | -- | 272 tok | 291 tok |
| 617 chars | -- | 287 tok | 308 tok |
| 815 chars | 317 tok | 326 tok | 351 tok |

Faster per token but 29% more tokens per character nets out to **46.3 chars/s of English, 27% slower
than qwen3.5 and 45% slower than qwen2.5**. On this English-only branch Sarvam is the slowest of the
three at the only thing the student actually perceives.

### Cache reuse: dense attention restores it, and this is the clean control

Each turn's excerpts sit in the system message, so the strict-extension cache only survives a
follow-up when retrieval returned the *same* excerpts. Splitting the follow-ups on that:

| day | turn | ctx chars | prev ctx | same prefix? | prefill ms/tok |
| --- | --- | --- | --- | --- | --- |
| 23 Sep qwen3.5 | fabacdf73043 | 617 | 617 | **YES** | 10.38 |
| 23 Sep qwen3.5 | 4b8af6285a85 | 643 | 643 | **YES** | 9.41 |
| 23 Sep qwen3.5 | 6f0cd8b4d948 | 614 | 483 | no | 9.23 |
| 23 Sep qwen3.5 | 326a01a33fc5 | 643 | 614 | no | 9.45 |
| 24 Sep Sarvam | 8c558909c91a | 610 | 610 | **YES** | **3.22** |
| 24 Sep Sarvam | 65e7eb05ddca | 483 | 815 | no | 7.70 |

qwen3.5 pays a full re-prefill *even when the prefix is identical* -- that is the recurrent
architecture, and it is now confirmed twice with the prefix held constant rather than inferred.
Sarvam, given the same identical prefix, drops to 3.22 ms/tok, matching qwen2.5's dense-reuse
signature (3.11-3.78 ms/tok across 6 of its 8 follow-ups). The prediction that being dense would
restore cache reuse **holds**. Caveat: n=2 follow-ups on Sarvam, one of each kind. The mechanism is
now explained rather than guessed, but a longer run would firm it up.

### Quality signal, weak but consistent with the Mac testing

Median answer 319 chars against qwen3.5's 596, with two stub answers of 53 and 73 characters. That
is the instruction-following weakness showing up on device, not a latency artefact.

### Open question

The logs do not say which template shipped. If this ran the stock `hf.co/bartowski/...` tag rather
than `sarvam1-tutor:2b`, the answers carry a leaked ` </s>` and ~10 junk tokens per turn, and the
prompt-token counts above are inflated by roughly that much. Worth confirming before the numbers are
quoted anywhere.
