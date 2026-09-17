# EXP-XXX — Small-model shortlist to replace qwen2.5:1.5b

**Approach:** English-only (the tokenizer finding in §5d also applies to Multilingual)
**Owner:** Mayur | **Date started:** 12 Sep 2026
**Date closed:** 12 Sep 2026 | **Status:** Worked — shortlist and runtime checks are done, but the quality half of the hypothesis is still untested (see §9)
**Device tested on:** Dev machine only — Intel Mac, Core i7-9750H (6 cores, AVX2), 16 GB, macOS 26.6.2 (25G83). Nothing was run on the Windows target laptop; its figures below are projections from its exp005/exp006 measurements.
**Related experiments:** exp004 (groundedness marking) · exp005/exp006 (context-budget sweep on the target, source of the latency baseline) · LFM2.5-1.2B vs qwen2.5 ABBA, 11 Sep (the trigger) · Groundedness harness v1/v2, 16 Sep (the instrument for the follow-up)

Full visual report: https://claude.ai/code/artifact/71374200-be70-443d-9844-02b3d8b6ccb4

---

## 1. Context

The English-only tutor runs `qwen2.5:1.5b` (Q4_K_M) on Ollama 0.12.3. The Windows installer pins that runtime version. The target laptop (Intel i5-1145G7, 4 cores) has no GPU backend, since 0.12.3 ships no Vulkan build, so everything runs on the CPU. A turn there is mostly prompt reading:

- **Prompt reading:** ~25.6 ms per uncached prompt token.
- **Generation:** 15.6 tokens/s.
- **New question:** a new question at the 800-character context budget reaches its first word in ~4.1 s (exp006 mean: 4.06 s).
- **Follow-ups:** only reach 0.6–1.7 s because Ollama reuses its KV cache when a new prompt strictly extends the previous one.

Correctness was the open problem:

- **exp004:** 9 of 21 answers wrong (7 correct, 5 partly correct).
- **exp006:** about a third wrong at every budget.

Most errors tracked bad evidence: exercise pages outranking definitions, and passages cut by the budget. Some did not. The model overrode a correct passage ("joints are of two types" became three), and it wrote headings and bullets that the prompt forbids.

The trigger was the 11 Sep test of LFM2.5-1.2B as a faster drop-in. It generated 31% faster, but on 0.12.3 it got no cache reuse at all, and it made 7 wrong answers of 20 against qwen's 4. That raised the broader question: does any small model beat qwen2.5 on this hardware?

That test also left two lessons going in:

1. **Architecture matters as much as benchmark scores.** LFM's convolution layers carry state that cannot be rewound, so the cache that makes follow-ups fast is lost.
2. **Vendor benchmarks did not predict our task.** Liquid reports IFEval 86 for LFM2.5.

Constraints:

- **Hardware:** CPU only.
- **Runtime:** pinned at Ollama 0.12.3.
- **Answer length:** the prompt now asks for ~100-word answers (commit cb4d94c), so generation speed matters as well as prompt reading.
- **Multilingual:** the Hindi/Marathi branch runs `gemma2:2b`.

## 2. Hypothesis

*If we replace qwen2.5:1.5b with a newer sub-2B dense model that loads on the pinned Ollama 0.12.3, then grounded-answer errors will fall below qwen2.5's level, while time to first word on the target stays within +0.5 s of 4.1 s and follow-up cache reuse stays at or above 90%.*

Why we believed it:

- **qwen2.5:1.5b is weak for its class.** It is from Sep 2024 and scores near the bottom of its size class on public faithfulness and instruction-following tests: 15.8% hallucination on Vectara's grounded-summary leaderboard, and IFEval 42.5. Its 2025 successors at the same size report several times fewer unsupported claims.
- **Prompt reading costs track decoder size.** On this CPU, reading the prompt is compute-bound, and the compute per token follows the decoder's parameter count. Token embeddings are table lookups, and the output head runs only for the last prompt token. So a model with a similar decoder should cost similar time. The measured LFM2.5 speeds matched this rule within a few percent.
- **Dense attention should keep the cache.** A dense-attention model should keep strict-extension cache reuse, which LFM2.5 lost because of its recurrent layers.
- **Qwen3 is a drop-in format.** It shares qwen2.5's tokenizer and ChatML chat format, so the prompt, budget and benchmark carry over unchanged.

## 3. Why this approach over the alternatives

The approach had three parts, all done before spending full benchmark runs:

1. Desk research to build a shortlist.
2. Exact parameter counts to project target latency.
3. Short runtime probes of the finalists on the pinned Ollama.

| Option considered | Why not chosen |
| --- | --- |
| Run the full ABBA benchmark (`benchmark.py`, 20 hand-marked answers) on every candidate | About 20 candidates, each taking hours on the dev machine plus manual marking, and several cannot even load on 0.12.3. Kept for the two finalists (see §9). |
| Pick from public leaderboards alone | LFM2.5 leads its class on IFEval (86) yet made more errors than qwen in our run. Leaderboards also say nothing about whether a model loads on 0.12.3 or keeps the cache. |
| Move up to a 3–4B model for quality | Projected at 2–3.6× today's compute per token: ~9–21 s to first word and 25–45 s per 100-word answer on the target. |
| Upgrade Ollama first, to unlock Qwen3.5 and Gemma 4 and possibly iGPU prefill | A packaging change with its own risk. Qwen3.5's recurrent layers would still lose the cache. Parked as its own experiment. |
| LFM2.5-1.2B | Tested 11 Sep: no cache reuse on 0.12.3, and 7 vs 4 wrong answers. Rejected. |
| Fine-tune qwen2.5 or another small model on textbook explanations | Needs a training set and a pipeline. Premature until the base model is chosen. |
| Keep the model, fix only retrieval and prompt | Running in parallel (corpus filtering, budget, re-chunking) and needed regardless. It does not address the model overriding a correct passage or ignoring format rules. |
| India-first models (Sarvam-30B, BharatGen Param2-17B, Sarvam-1 2B) | The first two are far too large for the target laptop. Sarvam-1 is a base model with no chat tuning. |
| Switch runtime (llama.cpp server, OpenVINO) | Not evaluated. The installer, warm-up and cache-friendly prompt layout are all built around Ollama, and switching would restart the latency work. |

## 4. What we did — step by step

All scripts ran from a Claude Code session scratchpad under `/private/tmp`, which has since been cleared (§7, Failure 6). The essential code is inlined below; the full sources survive in the session transcript.

1. **Listed candidates.**
   - **Method:** web search for small open-weight models released up to Aug 2026, plus the 2024–25 small models already in Ollama's library.
   - **New since the last look:** Qwen3.5 0.8B/2B/4B (Mar 2026), Gemma 4 E2B/E4B (Apr 2026), Granite 4.1 3B (Apr 2026) and 4.2 3B (Aug 2026), and Ministral 3 3B (Dec 2025).
   - **No small sizes:** Qwen3.6 and Qwen3.8 have no model under 27B.

2. **Checked which architectures the pinned runtime can load.** Downloaded the official Ollama v0.12.3 macOS release into a scratch folder and searched the binary for each llama.cpp architecture name:

   ```bash
   curl -LO https://github.com/ollama/ollama/releases/download/v0.12.3/ollama-darwin.tgz
   tar xzf ollama-darwin.tgz
   for a in qwen2 qwen3 qwen3next qwen35 gemma3 gemma3n gemma4 llama phi3 granite granitehybrid \
            smollm3 lfm2 exaone4 falcon-h1 gpt-oss mistral3; do
     echo "$a=$(strings ollama | grep -cx "$a")"
   done
   ```

   - **Present:** qwen3, gemma3, gemma3n, llama, phi3, granite, granitehybrid, smollm3, lfm2, exaone4, falcon-h1, gpt-oss.
   - **Absent:** qwen35, qwen3next, gemma4, mistral3.
   - **Caveat:** a string match is necessary, not sufficient, so qwen3, gemma3 and granite were also loaded live in step 7.

3. **Counted exact parameters without downloading weights.**
   - **Method:** read each model's safetensors header over HTTP range requests (an 8-byte length, then a JSON header).
   - **Buckets:** decoder, token embedding, output head, per-layer embeddings (Gemma 3n/4), and vision/audio towers.
   - **What matters:** only the decoder is paid per prompt token.

   ```python
   n = struct.unpack("<Q", get(url, rng=(0, 7)))[0]
   header = json.loads(get(url, rng=(8, 8 + n - 1)))   # {tensor_name: {"shape": [...]}}
   ```

   - **Detour:** macOS's system `python3` failed TLS verification against huggingface.co (log in §8). Re-ran it with the backend venv's Python and `SSL_CERT_FILE` pointed at its certifi bundle.
   - **Attention layout:** taken from each `config.json` (`layer_types`, `sliding_window`, `num_kv_shared_layers`, `full_attention_interval`).

4. **Projected target latency.**
   - **Anchor:** qwen2.5:1.5b on the target — 25.6 ms per uncached prompt token, 15.6 tok/s, and ~160 uncached tokens for a new question at budget 800 (4.1 s to first word).
   - **First word** = 4.1 s × (decoder params ÷ 1.31B) × English token ratio. Recurrent models cannot reuse the ~120-token persona prefix, so for them all ~280 prompt tokens count.
   - **Generation** = 15.6 tok/s × 1.54B ÷ (decoder + output-head params).
   - **Answer:** fixed at 130 tokens (~100 words) for every model.
   - **Check:** the rule predicted LFM2.5 at +32% generation and −21% prefill; the 11 Sep run measured +31% and −15 to −30%.

5. **Collected quality evidence.**
   - **Faithfulness:** the Vectara hallucination leaderboard, HHEM-2.1 snapshot of 7 Oct 2025, fetched through the GitHub commits API (commit `279c928`). The current May 2026 board uses a new dataset that dropped most small models, including qwen2.5-1.5B, and web.archive.org could not be fetched from the tooling.
   - **Instruction following:** Qwen3 Technical Report, Table 20. It scores qwen2.5-1.5B, Qwen3-0.6B/1.7B, Gemma-3-1B and Phi-4-mini with one harness, non-thinking. Vendor model-card numbers are used elsewhere and flagged as not comparable across vendors.
   - **Licences:** Hugging Face API `cardData` and each LICENSE file.

6. **Measured tokenizer cost.**
   - **Tools:** `tokenizers` 0.23.2 in a scratch venv (the backend venv doesn't include it), with each model's `tokenizer.json` from Hugging Face.
   - **English text:** 12,755 characters from PDF pages 20, 21, 60, 61, 110, 111, 120 and 121 of `data/PDF English/Class6_Sci_book.pdf`, extracted with pypdf.
   - **Hindi and Marathi:** our own translations of the p.111 shadow passage (338 and 331 characters). The repo has no Indic textbook.

7. **Probed the runtime, in isolation.** The v0.12.3 binary ran on its own port and model store, so the main Ollama (0.32.15, `~/.ollama`), which caches across runs, was never touched:

   ```bash
   OLLAMA_HOST=127.0.0.1:11500 OLLAMA_MODELS=<scratch>/models OLLAMA_NOPRUNE=1 \
   OLLAMA_CONTEXT_LENGTH=4096 OLLAMA_KEEP_ALIVE=-1 ./ollama serve
   OLLAMA_HOST=127.0.0.1:11500 ./ollama pull qwen3:1.7b    # also qwen3:0.6b, gemma3:1b, granite4:1b
   ```

   For each model, `probe_cache.py` sent the tutor's real system prompt to `/api/chat`:
   - **Prompt:** `build_system_prompt(TutorProfile(level="Class 6", subject="General Science", language="English", style="socratic"), excerpt)`.
   - **Options:** `num_ctx 4096`, `temperature 0.3`, `num_predict 160`, `seed 7`.
   - **Turns:**
     - **T1:** p.111 shadow excerpt + "What is a shadow?" — cold, right after load.
     - **T2:** T1 + its answer + "Why does it change length during the day?" — a strict extension, i.e. the follow-up case.
     - **T3:** a short magnet-poles passage (paraphrased, not verbatim from the book) + "What are the poles of a magnet?" — shares only the persona prefix.
     - **Cold references:** T2 and T3 again, each after an unload (`keep_alive: 0`) and reload.
   - **Metric:** reuse = 1 − warm prefill ms ÷ cold prefill ms.
   - **Detour:** `prompt_eval_count` reports the full prompt length even on a cache hit (warm and cold counts were identical), so only `prompt_eval_duration` shows reuse.

8. **Found and fixed the Qwen3 cache break.**
   - **Symptom:** `qwen3:1.7b` with `think: false` reused only 59% on the follow-up.
   - **Diagnosis:** `ollama show --template qwen3:1.7b` showed why (§7, Failure 1).
   - **Fix:** a derived model whose template renders the empty think block before every assistant turn and never adds `/no_think`. Requests to it send no `think` field.

   ```
   FROM qwen3:1.7b
   TEMPLATE """{{- if .System }}<|im_start|>system
   {{ .System }}<|im_end|>
   {{ end }}
   {{- range $i, $_ := .Messages }}
   {{- $last := eq (len (slice $.Messages $i)) 1 -}}
   {{- if eq .Role "user" }}<|im_start|>user
   {{ .Content }}<|im_end|>
   {{ else if eq .Role "assistant" }}<|im_start|>assistant
   <think>

   </think>

   {{ .Content }}{{ if not $last }}<|im_end|>
   {{ end }}
   {{- end }}
   {{- if and (ne .Role "assistant") $last }}<|im_start|>assistant
   <think>

   </think>

   {{ end }}
   {{- end }}"""
   ```

   Then `ollama create qwen3-tutor:1.7b -f Modelfile.qwen3-1.7b` (and the same for 0.6b), and the probe was re-run.

9. **Probed Granite despite a surprise download.** `granite4:1b` pulled 3.3 GB where ~1 GB was expected. The tag is BF16, not Q4 (§7, Failure 3). It was probed anyway, because loading and cache behaviour don't depend on quantisation.

10. **Published the comparison** as the visual report linked at the top of this page.

**Environment**

- **Models:** `qwen2.5:1.5b` Q4_K_M (Ollama digest `65ec06548149`); `qwen3:1.7b`, `qwen3:0.6b` and `gemma3:1b` (Ollama library default tags, pulled 12 Sep 2026); `granite4:1b` (Ollama tag, BF16); the derived `qwen3-tutor:1.7b` and `qwen3-tutor:0.6b`. LFM2.5 figures come from `hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q4_K_M` (11 Sep run).
- **Libraries:** `tokenizers` 0.23.2, pypdf, Python 3.12.
- **Runtime:**
  - Official Ollama 0.12.3 macOS release binary, CPU only, isolated on port 11500.
  - Server environment: `OLLAMA_CONTEXT_LENGTH=4096`, `OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_NOPRUNE=1`, flash attention off (the default).
  - Per-request options: `num_ctx 4096`, `temperature 0.3`, `num_predict 160`, `seed 7`.
- **Hardware and OS build:** Intel Core i7-9750H (6 cores, AVX2), 16 GB, macOS 26.6.2 (25G83). The target laptop was not used; its anchor numbers come from exp005/exp006 (Intel i5-1145G7, 4 cores, AVX-512, Windows, Ollama 0.12.3).
- **Baseline:** `qwen2.5:1.5b` Q4_K_M, used three ways:
  - the same probe on the same runtime, for dev-machine ratios;
  - exp005/exp006, for target latency;
  - the hand-marked 11 Sep ABBA run, for answer correctness.

## 5. What we measured

### 5a. Headline metrics — baseline vs the leading candidate

| Metric | Baseline: qwen2.5:1.5b | After: Qwen3-1.7B (`qwen3-tutor` template) | Target | Met? |
| --- | --- | --- | --- | --- |
| Cold start (model load) | Not measured | Not measured | — | — |
| Time to first word, new question (target laptop) | 4.1 s | ≈4.5 s (projected) | ≤ 4.6 s | Yes — projected only |
| Generation speed (target laptop) | 15.6 tok/s | ≈13 tok/s (projected) | None set | — |
| End-to-end, new question + 100-word answer (target laptop) | ≈12.4 s | ≈14.4 s (projected) | None set | — |
| Follow-up cache reuse (dev machine, 0.12.3) | 94% | 94% (stock template: 59%) | ≥ 90% | Yes, with the template fix |
| New-question prefix reuse (dev machine, 0.12.3) | 62% | 63% | No regression | Yes |
| Peak RAM | Not measured | Not measured | — | — |
| Package size (model download) | ~1.0 GB | ~1.4 GB | None set | — |
| Accuracy: Vectara hallucination rate (public) | 15.8% | 4.4% | Below baseline | Yes — public proxy |
| Accuracy: IFEval strict prompt (Qwen3 report) | 42.5 | 68.2 | Above baseline | Yes — public |
| Accuracy: wrong answers, our 20 marked questions | 4 of 20 (11 Sep ABBA) | Not run | Fewer than baseline | **Not tested** |
| WER | n/a — no speech component | n/a | — | — |

How each number was measured:

- **Targets:** the +0.5 s and 90% thresholds come from the hypothesis. No targets were agreed in advance for generation speed, package size or RAM.
- **Target first word and generation (baseline):** measured on the target laptop in exp005/exp006 (90 turns).
- **Target first word and generation (Qwen3):** the baseline anchor × the dev-machine ratio. The prefill ratio was 1.05× and 1.18× in two runs, with the same weights and only the chat template differing. The generation ratio was 0.86× and 0.82×. These are projections, not device runs.
- **End-to-end:** first word + 130 tokens ÷ generation rate.
- **Cache reuse:** one warm/cold pair per model on the dev machine (T2 and T3 in §4 step 7); each cold run followed an unload.
- **Dev-machine ratios:**
  - Prefill: summed prefill ms ÷ summed prompt tokens over the two cold turns, relative to qwen2.5's same turns.
  - Generation: from T1 (up to 160 tokens).
  - Noise: about ±10% run to run.
- **Vectara:** HHEM-2.1 board of 7 Oct 2025. It scores summaries of supplied news-style articles, with Qwen3 run with thinking off. It is a proxy for "answer from the excerpt", not our task.
- **IFEval:** strict prompt-level score, non-thinking, from Qwen3 Technical Report Table 20.
- **Wrong answers:** set B of the 11 Sep ABBA run, marked by hand against the book.
- **Package size:** Ollama library listing sizes.

### 5b. All runtime probes (dev machine, Ollama 0.12.3, one run each)

| Model | Prefill vs qwen2.5 | Generation vs qwen2.5 | Follow-up reuse | New-question reuse |
| --- | --- | --- | --- | --- |
| qwen2.5:1.5b (baseline) | 1.00× (13.9 ms/token) | 1.00× (14.6 tok/s) | 94% | 62% |
| qwen3:1.7b, stock template, `think:false` | 1.18× | 0.82× | **59%** | 66% |
| qwen3-tutor:1.7b (fixed template) | 1.05× | 0.86× | 94% | 63% |
| qwen3:0.6b, stock template, `think:false` | 0.50× | 1.86× | **53%** | 57% |
| qwen3-tutor:0.6b (fixed template) | 0.49× | 2.03× | 93% | 62% |
| gemma3:1b | 0.85× | 1.23× | 95% | 63% |
| granite4:1b (BF16 tag — speed not representative) | 0.70× | 0.58× | 93% | 57% |
| LFM2.5 1.2B Q4_K_M (11 Sep, separate run) | ≈0.70–0.85× (on 0.32.15) | 1.31× | **0%** (turn 2: 1,093 ms vs qwen 160 ms) | None observed |

### 5c. Every candidate against qwen2.5:1.5b (target laptop, projected unless stated)

| Model | Verdict | First word · generation | Pros vs qwen2.5:1.5b | Cons vs qwen2.5:1.5b |
| --- | --- | --- | --- | --- |
| **qwen2.5:1.5b** (Qwen, Sep 2024, Apache 2.0) | Baseline | 4.1 s · 15.6 tok/s (measured) | Measured on the device; prompt and budget were tuned on it; the stock template keeps the cache (94%). | Vectara 15.8%; IFEval 42.5; ~1 token per Devanagari character. |
| **Qwen3-1.7B** non-thinking (Apr 2025, Apache 2.0) | A/B first | ≈4.5 s · ≈13 tok/s | Vectara 4.4%; IFEval 68.2; multilingual instruction following (Multi-IF) 44.7 vs 20.2; MMLU-Redux 64.4 vs 50.7; same tokenizer and chat format; loads on 0.12.3; 119 languages including Hindi and Marathi. | Needs the template fix (59% reuse without it); ~15% slower generation; thinking must stay off; same Devanagari cost; one of two magnet-poles answers still had an error. |
| **Granite 4.0 1B** (IBM, Oct 2025, Apache 2.0) | A/B second | ≈4.4 s · ≈15 tok/s (for Q4) | IFEval 77.4 and MMLU 59.4 (IBM's own numbers); loads as dense `granite` and keeps 93% reuse with the stock template; both probe answers correct. | No Hindi or Marathi; no Vectara score for the 1B; Ollama's tag is BF16 at 3.3 GB, so it needs a Q4 GGUF. |
| **Qwen3-0.6B** non-thinking (Apr 2025, Apache 2.0) | Speed floor | ≈2.0 s · ≈30 tok/s | About 2× faster both ways; Vectara 3.7%; IFEval 54.5. | Less knowledge (MMLU-Redux 44.6); inverted magnet poles in both runs; needs the template fix. |
| **Gemma 3 1B** (Google, Mar 2025, Gemma terms) | Speed floor | ≈3.7 s · ≈19 tok/s (measured ratio) | Faster; Vectara 5.3%; IFEval 54.5; 95% reuse despite sliding-window attention; 3.6× fewer Marathi tokens. | Least knowledge (MMLU-Redux 33.3); inverted magnet poles; custom Gemma licence; no system role (Ollama folds it into the first user turn). |
| **Llama 3.2 1B** (Meta, Sep 2024, Llama licence) | Reject | ≈3.0 s · ≈19 tok/s | Faster; Hindi officially supported. | Vectara 20.7%, worse than baseline; licence requires "Built with Llama" attribution. |
| **SmolLM2 1.7B** (Hugging Face, Nov 2024, Apache 2.0) | Reject | ≈5.4 s · ≈14 tok/s | Fully open training data; IFEval 56.7. | English only; 8k context; slower both ways; second-worst Marathi tokenizer tested; no Vectara score. |
| **LFM2.5 1.2B** (Liquid AI, 2026, LFM licence) | Reject — measured 11 Sep | ≈5.7 s · ≈20 tok/s | 31% faster generation; hits the 100-word target. | No cache reuse on 0.12.3; 7 vs 4 wrong answers of 20; free only under $10M annual revenue; no Indic languages; worst Marathi tokenizer tested. |
| **Gemma 3n E2B** (Google, Jun 2025, Gemma terms) | Multilingual branch — now | ≈6–10 s · ≈10 tok/s | Loads on 0.12.3; decoder 1.91B vs `gemma2:2b`'s 2.03B; Global-MMLU-Lite 59.0; 3.6× fewer Marathi tokens than Qwen; audio input. | Slower than qwen2.5 in English; 5.6 GB Ollama tag; cache reuse not verified; Gemma licence; no Vectara score. |
| **Gemma 4 E2B** (Google, Apr 2026, Apache 2.0) | Multilingual branch — after upgrade | ≈6–10 s · ≈10 tok/s | MMLU-Pro 60.0 and MMMLU 67.4 (vendor); 140+ languages; efficient tokenizer; 20 of 35 layers share KV. | Needs Ollama 0.20+; thinks by default; recommended temperature 1.0; 7.2 GB default tag (3.1 GB Q4 GGUF); llama.cpp had a cache-reuse bug (#21468, closed). |
| **Qwen3.5 0.8B / 2B** (Mar 2026, Apache 2.0) | Reject on this runtime | ≈2.9 s / ≈8.1 s | 201 languages; halves Marathi tokens (486 vs 964); vision built in. | Recurrent: 18 Gated DeltaNet layers to 6 attention, the same cache loss as LFM; won't load on 0.12.3; Qwen warns the 0.8B falls into thinking loops; 2B IFEval 61.2 (vendor). |
| **Qwen3-4B-Instruct-2507** (Aug 2025, Apache 2.0) | Too slow here | ≈11 s · ≈6 tok/s | Vectara 2.7%; IFEval 81.2; no thinking to manage; loads on 0.12.3. | 2.8× compute per token: ~33 s per 100-word turn. |
| **Phi-4-mini 3.8B** (Microsoft, Feb 2025, MIT) | Too slow here | ≈10 s · ≈6 tok/s | MIT licence; IFEval 68.6; Vectara 3.4% (2025 board). | 2.5× compute; 23.5% on Vectara's harder 2026 set, with 420-word summaries; Hindi not in its language list. |
| **Gemma 3 4B** (Google, Mar 2025, Gemma terms) | Too slow here | ≈11 s · ≈6 tok/s | Vectara 3.7%; strong multilingual scores. | 2.5× compute; answered only 67% of Vectara's 2026 prompts. |
| **Llama 3.2 3B** (Meta, Sep 2024) | Too slow here | ≈8.7 s · ≈7.5 tok/s | Vectara 7.9%; IFEval 77.4; Hindi supported. | 2.2× compute: ~26 s per turn. |
| **Granite 4.1 / 4.2 3B** (IBM, Apr / Aug 2026, Apache 2.0) | Too slow here | ≈9.7 s · ≈7 tok/s | Dense and loads on 0.12.3; same shape as Granite-4.0-micro (Vectara 6.5%). | 2.4× compute; 4.2 thinks by default; no Indic languages. |
| **SmolLM3 3B** (Hugging Face, Jul 2025, Apache 2.0) | Too slow here | ≈8.7 s · ≈8 tok/s | Fully open data; IFEval 76.7 with thinking off. | 2.2× compute; six European languages; thinks by default. |
| **Qwen3.5 4B / Gemma 4 E4B** (2026, Apache 2.0) | Too slow here | ≈21 s / ≈13.5 s | Strongest 2026 vendor numbers (Qwen3.5-4B IFEval 89.8; Gemma 4 E4B MMLU-Pro 69.4). | 2.8–3.1× compute; both need an Ollama upgrade; Qwen3.5-4B is recurrent. |

Set aside without a projection:

- **Ministral 3 3B:** 24.2% on Vectara's 2026 board, and it answers only 74% of prompts.
- **Qwen2.5-3B:** non-commercial Qwen Research licence, unlike the 1.5B.
- **EXAONE 4.0 1.2B:** its licence prohibits commercial use.
- **Granite 4.0 H and Falcon-H1:** Mamba hybrids, so the same cache loss as LFM.
- **DeepSeek-R1-Distill-Qwen-1.5B:** reasons for hundreds of tokens before every answer.
- **gpt-oss-20b:** needs ~13 GB of RAM, and its 3.6B active parameters are 2.7× today's compute.

### 5d. Tokenizer cost — tokens per 1,000 characters

| Tokenizer | English (book text) | Hindi | Marathi |
| --- | --- | --- | --- |
| qwen2.5 / Qwen3 | 244.5 | 920 | 964 |
| Qwen3.5 | 251.7 | 408 | 486 |
| Gemma 3 / 3n / 4 | 260.7 | 246 | 269 |
| Llama 3.2 / SmolLM3 | 242.6 | 521 | 565 |
| Phi-4-mini | 239.7 | 302 | 357 |
| Granite 4 | 242.6 | 970 | 1,021 |
| SmolLM2 | 264.8 | 1,077 | 1,157 |
| LFM2.5 | 246.3 | 1,243 | 1,227 |

- **English:** all tokenizers are within 8% of each other.
- **Hindi and Marathi:** each figure comes from a single 331–338-character passage, so treat it as directional.
- **What it means on the target (arithmetic, not a timed run):** a 100-word Marathi answer is ~660 characters. That is ≈636 tokens for Qwen, or ≈40 s of generation at 15.6 tok/s, against ≈178 tokens for Gemma.

## 6. What worked

**Qwen3-1.7B fits the latency budget.**
- **Why:** its decoder has 1.41B parameters against qwen2.5's 1.31B, which is 8% more compute per prompt token. The dev machine measured 1.05–1.18×.
- **No token penalty:** its tokenizer is identical to qwen2.5's, so prompts don't get longer.
- **Cost:** it gives up ~15% of generation speed, because its output head is larger (311M vs 233M parameters).

**The template fix restored follow-up cache reuse (59% → 94%, and 53% → 93% for 0.6B).**
- **Why:** Ollama reuses its KV cache only for a token-identical prefix. The fixed template renders every past assistant turn exactly as it was generated, and puts nothing on a user turn that later moves.
- **Thinking stays off without the flag:** pre-filling an empty think block is how Qwen's own `enable_thinking=False` works, so no `think` field is needed.
- **Not yet known:** Qwen's official template strips think blocks from past turns. Whether keeping empty blocks there changes answer quality was not measured.

**Projecting speed from exact decoder size was good enough to rule most models in or out.**
- **Why:** on a CPU, reading the prompt is dominated by the decoder's matrix multiplies. Token embeddings are table lookups, and the output head runs only for the last prompt token. Generation reads the decoder plus the output head for every token.
- **Validation:** it predicted LFM2.5 within a few percent.
- **Limit:** it overstated Gemma 3 1B (Failure 2), so treat projections as ±50% for architectures we haven't measured.

**Searching the binary for architecture names was a fast, reliable filter.**
- **Why:** Ollama's bundled llama.cpp and its Go engine only load architectures they have names and code for.
- **Limit:** necessary but not sufficient, so the finalists were confirmed with live loads.

**Isolating the probe runtime made the cache numbers trustworthy.**
- **Why:** the main Ollama (0.32.15) keeps caches across runs, which inflated an earlier A/B. A separate port and model store, with an unload before every cold reference, removed that.

**Gemma 3 1B kept cache reuse despite sliding-window attention (95% / 63%).**
- **Why:** not established.
- **Caveat:** the probe conversations stayed under ~550 tokens, close to its 512-token window. Whether reuse survives longer sessions is untested.

**The Oct 2025 Vectara snapshot put the baseline and most candidates under one method.**
- **Why it mattered:** the current board would have left qwen2.5 without a comparable number.

## 7. What didn't work

**Failure 1 — The stock Qwen3 template broke the follow-up cache**

- **Symptom:** `qwen3:1.7b` follow-up prefill was 2,531 ms warm vs 6,181 ms cold (59% reuse), where qwen2.5 saved 94%. `qwen3:0.6b` reused 53%.
- **What we tried:** read the template with `ollama show --template qwen3:1.7b`, wrote a derived model with a rewritten template, and re-probed: 94% (1.7B) and 93% (0.6B).
- **Root cause:** with `think` set, the template does two things that break reuse:
  - it appends " /no_think" to the latest user message only;
  - it pre-fills an empty think block only on the reply being generated.

  On the next turn the previous question is no longer the latest, and the previous reply is replayed without the block. So the prompt stops being a strict extension right after the previous question. The lost time matches re-reading the previous answer (~160 tokens at ~15 ms/token).
- **Dead end, or just parked?** Fixed. If Qwen3 is adopted, it must ship as a derived model in the installer, and the backend must stop sending `think`.

**Failure 2 — The size projection overstated Gemma 3 1B's speed**

- **Symptom:** predicted prefill 0.53× and generation 1.54× of qwen2.5; measured 0.85× and 1.23×.
- **What we tried:** nothing further.
- **Root cause:** cause not identified.
- **Dead end, or just parked?** Parked. Gemma 3n/4 E2B projections are given as a range (size projection up to ×1.6) until measured.

**Failure 3 — Granite 4.0 1B's speed couldn't be measured from Ollama's tag**

- **Symptom:** `granite4:1b` downloaded 3.3 GB (16 × 204 MB parts), and `ollama show` reports BF16. Generation ran at 8.4 tok/s (0.58×) while prefill measured 0.70×.
- **What we tried:** probed it anyway for loading and cache behaviour, which quantisation doesn't affect.
- **Root cause:**
  - The library tag is unquantised BF16, so its speed doesn't represent a Q4 build.
  - Why BF16 prompt reading ran faster than qwen2.5's Q4_K_M: cause not identified.
- **Dead end, or just parked?** Parked. It needs a run from a Q4_K_M GGUF.

**Failure 4 — The newest small models can't run on the pinned runtime**

- **Symptom:** `qwen35`, `gemma4` and `mistral3` are absent from the 0.12.3 binary.
- **What we tried:** no workaround was attempted.
- **Root cause:** those architectures were added to Ollama after 0.12.3. Gemma 4's Ollama documentation asks for 0.20 or newer.
- **Dead end, or just parked?** Parked until an Ollama-upgrade experiment. For Qwen3.5 it is probably a dead end on this CPU regardless: 18 of its 24 layers are recurrent (Gated DeltaNet), the design that cost LFM2.5 its cache. llama.cpp also has open reports of it re-processing the full prompt every turn (#20225).

**Failure 5 — Sub-1B models misread a correct excerpt**

- **Symptom:**
  - Qwen3-0.6B wrote "unlike poles (south and south) attract each other", in both runs.
  - Gemma 3 1B wrote "When magnets are close together, the north and south poles push away from each other."
- **What we tried:** nothing; one seeded sample each.
- **Root cause:** cause not identified. One sample can't separate model weakness from sampling.
- **Dead end, or just parked?** Parked. Both stay on the list only as speed-floor options.

**Failure 6 — The probe scripts and raw outputs were lost**

- **Symptom:** by 17 Sep the session scratchpad was gone. That included `params.py`, `toks.py`, `project.py`, `probe_cache.py`, `chart.py`, the Modelfiles, the isolated model store and all JSON outputs.
- **What we tried:** nothing. The script sources and printed outputs survive in the Claude Code session transcript.
- **Root cause:** the scratchpad lived under `/private/tmp`, which macOS clears. Whether a restart or periodic cleanup removed it was not checked.
- **Dead end, or just parked?** Parked. Commit the probe and projection scripts under `scripts/eval/` before the follow-up A/B.

## 8. Error logs

System Python TLS failure while reading safetensors headers (§4 step 3):

```
Qwen/Qwen2.5-1.5B-Instruct               ERROR <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1010)>
Qwen/Qwen2.5-3B-Instruct                 ERROR <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1010)>
[trimmed: the same error for the remaining 22 repositories]
```

Backend venv has no tokenizer library (§4 step 6):

```
ModuleNotFoundError: No module named 'tokenizers'
```

Archive snapshot of the leaderboard not reachable (§4 step 5):

```
Claude Code is unable to fetch from web.archive.org
```

Architecture names in the Ollama 0.12.3 binary (§4 step 2):

```
qwen2=1 qwen3=1 qwen3moe=1 qwen3next=0 qwen35=0 qwen3vl=0 gemma2=1 gemma3=1 gemma3n=1 gemma4=0 gemma-embedding=0 llama=2 phi3=1 phimoe=1 granite=1 granitehybrid=1 granitemoe=1 smollm3=1 lfm2=1 exaone4=1 hunyuan-dense=1 falcon-h1=1 ernie4_5=1 nemotron_h=0 olmo2=1 olmo3=0 mistral3=0 seed_oss=0 apertus=0 gpt-oss=1 bailingmoe2=0 minicpm=1 arcee=1 dots1=1
```

Failure 1 — stock template, baseline for comparison, then the fixed template (`probe_cache.py` output):

```
== qwen2.5:1.5b  (think=None)
  T1 cold      prompt  235 tok  prefill   4260 ms  (18.1 ms/tok)  gen 160 tok   14.6 tok/s
  T2 follow-up warm  414 tok    343 ms   | cold  414 tok   5814 ms   -> reuse saved  94%
  T3 new q     warm  214 tok   1101 ms   | cold  214 tok   2900 ms   -> reuse saved  62%
  thinking output: none
  [trimmed: answers]

== qwen3:1.7b  (think=False)
  T1 cold      prompt  243 tok  prefill   3587 ms  (14.8 ms/tok)  gen 135 tok   12.0 tok/s
  T2 follow-up warm  396 tok   2531 ms   | cold  396 tok   6181 ms   -> reuse saved  59%
  T3 new q     warm  222 tok   1335 ms   | cold  222 tok   3970 ms   -> reuse saved  66%
  thinking output: none
  [trimmed: answers]

== qwen3:0.6b  (think=False)
  T1 cold      prompt  243 tok  prefill   1729 ms  (7.1 ms/tok)  gen 160 tok   27.2 tok/s
  T2 follow-up warm  421 tok   1416 ms   | cold  421 tok   3022 ms   -> reuse saved  53%
  T3 new q     warm  222 tok    622 ms   | cold  222 tok   1433 ms   -> reuse saved  57%
  thinking output: none
  [trimmed: answers]

== qwen3-tutor:1.7b  (think=None)
  T1 cold      prompt  239 tok  prefill   3393 ms  (14.2 ms/tok)  gen 160 tok   12.6 tok/s
  T2 follow-up warm  421 tok    361 ms   | cold  421 tok   6327 ms   -> reuse saved  94%
  T3 new q     warm  218 tok   1118 ms   | cold  218 tok   3029 ms   -> reuse saved  63%
  thinking output: none
  [trimmed: answers]
```

Failure 1 — the two template branches responsible (`ollama show --template qwen3:1.7b`):

```
{{- if eq .Role "user" }}<|im_start|>user
{{ .Content }}
{{- if and $.IsThinkSet (eq $i $lastUserIdx) }}
   {{- if $.Think -}}
      {{- " "}}/think
   {{- else -}}
      {{- " "}}/no_think
   {{- end -}}
{{- end }}<|im_end|>
[trimmed: assistant and tool branches]
{{- if and (ne .Role "assistant") $last }}<|im_start|>assistant
{{ if and $.IsThinkSet (not $.Think) -}}
<think>

</think>

{{ end -}}
{{ end }}
```

Failure 3 — Granite tag is unquantised:

```
time=2026-09-12T13:25:03.298+05:30 level=INFO source=download.go:177 msg="downloading 551fc8b33f10 in 16 204 MB part(s)"

  Model
    architecture        granite
    parameters          1.6B
    context length      131072
    embedding length    2048
    quantization        BF16

== granite4:1b  (think=None)
  T1 cold      prompt  231 tok  prefill   3581 ms  (15.5 ms/tok)  gen  91 tok    8.4 tok/s
  T2 follow-up warm  340 tok    244 ms   | cold  340 tok   3450 ms   -> reuse saved  93%
  T3 new q     warm  210 tok    794 ms   | cold  210 tok   1856 ms   -> reuse saved  57%
```

Failure 5 — magnet-poles answers with the correct excerpt in the prompt:

```
== qwen3-tutor:0.6b  (think=None)
  T3 answer (401 chars): A magnet has two ends called poles. One end is the north pole, and the other is the south pole. Like poles (north and north) repel each other, and unlike poles (south and south) attract each other. A freely suspended magnet always comes to rest in the north-south direction.   /  / A magnet can be used to make things move or stay in place, like a compass or a toy magnet. What do you think about magnets

== gemma3:1b  (think=None)
  T3 answer (668 chars): Okay, imagine a magnet like a tiny, invisible force field. It has two sides, like two halves of a coin. These sides are called the poles.  /  / One side is called the north pole, and the other is called the south pole.  They’re opposite each other.   /  / When magnets are close together, the north and south poles push away from each other.  If they’re far apart, they pull towards each other.   /  / Think of i
[trimmed: answers are cut at 400 characters by the probe's printout]
```

Failure 6 — scratchpad gone:

```
ls: /private/tmp/claude-502/-Users-mayur-Projects-AI-Labs-AI-tutor-poc/14a94b7b-8820-45a1-bb98-3bcb2a0e4363/scratchpad/research: No such file or directory
```

## 9. Conclusion and next step

**The hypothesis is partly supported.** Qwen3-1.7B meets every criterion we could check without our own benchmark:

- 4.4% vs 15.8% on Vectara's hallucination leaderboard;
- IFEval 68 vs 42;
- projected +0.4 s to first word;
- 94% follow-up cache reuse once its template is fixed.

The criterion that matters most — fewer wrong answers on our Class 6 questions — is untested. For the approach as a whole, this CPU caps the model at roughly 1.5–2B parameters, so further correctness gains must come mainly from retrieval and prompt evidence, not from a bigger model.

- [x] Verdict: **park** — keep qwen2.5:1.5b until the A/B below
- [x] Follow-up experiments:
  - **Main A/B:** `qwen3-tutor:1.7b` and Granite 4.0 1B (Q4_K_M GGUF) against qwen2.5:1.5b, run ABBA with `benchmark.py --set both --budgets 800`, answers marked against the book, plus `scripts/eval/groundedness_eval.py` for claim-level faithfulness. Adopt a challenger only if wrong answers drop without first word rising more than ~0.5 s.
  - **Multilingual branch:** Gemma 3n E2B against `gemma2:2b`, with cache reuse checked the same way.
  - **Ollama upgrade:** evaluated as its own experiment (it unlocks Gemma 4 E2B and possibly iGPU prefill).
- [ ] Code or docs updated: no repo code changed. The visual report was published (link at top). The probe scripts still need to be committed under `scripts/eval/` (Failure 6).
- [ ] Shared with team on:

---

**References**

- Vectara hallucination leaderboard, HHEM-2.1, 7 Oct 2025: https://github.com/vectara/hallucination-leaderboard/blob/279c928fee126b0616b087c00267b47ff12f1a5a/README.md
- Vectara current board (HHEM-2.3, May 2026): https://github.com/vectara/hallucination-leaderboard
- Qwen3 Technical Report (Tables 18, 20): https://arxiv.org/abs/2505.09388
- Model cards:
  - Qwen3.5-2B: https://huggingface.co/Qwen/Qwen3.5-2B
  - Gemma 4 E2B: https://huggingface.co/google/gemma-4-E2B-it
  - Gemma 3n E2B: https://huggingface.co/google/gemma-3n-E2B-it
  - Granite 4.0 1B: https://huggingface.co/ibm-granite/granite-4.0-1b
  - Llama 3.2 1B: https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct
  - LFM2.5-1.2B: https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct
- Artificial Analysis on Qwen3.5 small models: https://artificialanalysis.ai/articles/qwen3-5-small-models
- llama.cpp #20225 (Qwen3.5 re-processes the full prompt every turn): https://github.com/ggml-org/llama.cpp/issues/20225
- llama.cpp #21468 (Gemma 4 cache reuse): https://github.com/ggml-org/llama.cpp/issues/21468
- Ollama gemma4 tags: https://ollama.com/library/gemma4/tags
