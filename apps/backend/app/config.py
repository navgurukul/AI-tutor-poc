"""Application settings.

Everything is overridable through environment variables or a `.env` file so the
frontend developer can point the backend at a different Ollama host or model
without touching code.
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "AI Tutor POC"
    version: str = "0.1.0"

    # --- Ollama -----------------------------------------------------------
    ollama_host: str = "http://localhost:11434"
    # One model for every language. gemma2:2b, not qwen2.5:1.5b: the 1.5B model
    # can't produce coherent Hindi/Marathi at all. A per-language split (English
    # on the smaller model) was tried and reverted -- on the 4 GB target every
    # language switch reloaded a model, which was slower than just running one.
    ollama_model: str = "gemma2:2b"
    # Keep the model resident in RAM between questions. Ollama unloads it after
    # 5 min idle by default, so the next question eats the full cold load again
    # (~10-20s on a 4 GB CPU). "-1" = never unload; a duration like "30m" also
    # works. On a 4 GB box this is the single biggest felt-latency fix.
    ollama_keep_alive: str = "-1"
    # Load the model into RAM when the backend starts (background task, doesn't
    # delay startup), so the first question isn't the one that pays the cold
    # start. Set false only if you don't want the backend touching Ollama on boot.
    warm_model_on_startup: bool = True
    # A small model on CPU is usually quick, but a long answer plus a cold model
    # load can still take a while, so the read timeout is generous.
    ollama_timeout_seconds: float = 180.0
    ollama_connect_timeout_seconds: float = 5.0

    # Ollama unloads an idle model after 5 minutes by default, and reloading
    # this one costs ~2s -- a student who pauses between questions would pay it
    # every time. Accepts Ollama's own forms: a number of seconds ("-1" never
    # unloads, "0" unloads immediately) or a duration ("30m", "1h").
    ollama_keep_alive: str = "-1"
    # Load the model at boot so the first question of the session doesn't pay
    # the load cost. Runs in the background; startup never waits on it.
    warm_model_on_startup: bool = True

    # --- Generation defaults ---------------------------------------------
    temperature: float = 0.7
    # Non-English turns run a touch lower than English (a little less script
    # drift) but NOT low -- under ~0.5 a small model loops phrases in Hindi. An
    # explicit per-request temperature still wins.
    temperature_non_english: float = 0.6
    # A mild anti-repetition nudge over Ollama's 1.1 default. Do not push past
    # ~1.2: Devanagari function words legitimately repeat a lot, and a hard
    # penalty makes the model swap them for rare junk tokens (word salad).
    repeat_penalty: float = 1.15
    repeat_last_n: int = 128
    # A tutor answer is 2-3 short sentences plus an example. Low on purpose — it's
    # the biggest CPU-latency lever, and Hindi costs 2-4x more tokens per word.
    # Raise it if answers get cut off mid-sentence.
    max_tokens: int = 200
    # Sized for the worst Devanagari case, not the English one. Four 2,000-
    # character Hindi passages are ~5,800 tokens on their own; with the system
    # prompt, breadcrumbs and replayed history the window has to hold roughly
    # 4,000 even after rag_context_token_budget caps the excerpts. At 3072 --
    # where the speech branch had left it, and where the merge silently kept it
    # -- Ollama truncates from the front and drops the system prompt without
    # raising anything.
    #
    # This costs prefill time and KV cache. Both are re-measured in phase 07;
    # the 1.6 GB / 3.3 GB resident figures in the decision record were taken at
    # a smaller window and do not hold here.
    num_ctx: int = 6144

    # --- Conversation memory ---------------------------------------------
    # Number of past messages (user + assistant) replayed to the model. Kept
    # short: every replayed turn is re-processed on CPU each request.
    max_history_messages: int = 10
    session_ttl_minutes: int = 180
    max_sessions: int = 500

    # --- Offline speech-to-text for the Indian languages --------------
    # sherpa-onnx + AI4Bharat IndicConformer-600M (CTC). Used for Hindi /
    # Marathi (English is recognised on-device by the browser). The folder
    # (the ONNX file + tokens.txt) is placed by scripts/setup.ps1; a relative
    # path is resolved against apps/backend/. Missing files -> /api/stt reports
    # "not ready" instead of breaking the app.
    #
    # Default is the fp32 export (`model.onnx`, ~470 MB): int8 roughly doubles
    # the word-error rate (Hindi CTC ~0.16 -> ~0.30) and the RAM saved (~280 MB)
    # isn't worth it here. Set STT_MODEL_FILE=model.int8.onnx to trade accuracy
    # for footprint on a tighter device.
    stt_model_dir: str = "models/indicconformer"
    stt_model_file: str = "model.onnx"
    # Decode is CPU-bound and nothing else runs during it (the LLM turn hasn't
    # started yet), so give it more threads. Lower it if the box has <4 cores.
    stt_num_threads: int = 4

    # --- Offline text-to-speech -------------------------------------------
    # sherpa-onnx + a Piper VITS voice (no extra dependency — sherpa is already
    # installed for STT). Only non-English answers route here (English uses the
    # OS speechSynthesis voice). The voice folder (<voice>.onnx, tokens.txt,
    # espeak-ng-data/) is placed by scripts/setup.ps1.
    tts_model_dir: str = "models/tts"
    tts_voice: str = "vits-piper-hi_IN-priyamvada-medium"
    tts_num_threads: int = 2
    # Playback speed multiplier. 1.0 = the voice's natural pace; lower is slower
    # (0.9 if it sounds rushed), higher is faster.
    tts_speed: float = 1.0

    # --- Per-turn metrics --------------------------------------------------
    # Attach the timing and retrieval trace to every reply, and write one INFO
    # line per turn. On by default: this is a POC whose whole latency story is
    # invisible without it, and the cost is a few hundred bytes and roughly a
    # millisecond of trigram sets against turns measured in seconds.
    #
    # Turn it off for a student-facing build, where the panel is noise and the
    # numbers are nobody's business, or when profiling something else and the
    # log line is in the way. Off means: no `metrics` on ChatResponse, no
    # `metrics` in the SSE `done` frame, no log line, and no groundedness
    # computed at all -- the frontend panel then has nothing to render, so it
    # disappears without needing its own switch. (VITE_SHOW_METRICS hides the
    # panel while leaving the numbers on the wire, which is the other half of
    # the same control.)
    metrics_enabled: bool = True

    # --- Retrieval (RAG) ---------------------------------------------------
    # Textbook retrieval is additive: if the store can't be opened the tutor
    # still answers from the model alone, so a missing library is a degraded
    # feature rather than a broken app.
    rag_enabled: bool = True
    # Kept beside the backend package so it travels with the app; the whole
    # corpus (text + vectors) is one file that can be built centrally and
    # copied onto a device, which is the only sane option on a 15W laptop.
    rag_db_path: str = "data/library.db"
    # bge-m3, not nomic-embed-text. Measured on the mixed-library case -- a
    # Hindi question against an English page -- nomic scored an off-topic
    # passage *higher* than the one that answers it. A negative margin means
    # Hindi retrieval is worse than random, and it fails silently. bge-m3 is
    # the only model tested that ranks Hindi->English and Marathi->English
    # correctly. It costs 1024 dims and ~3.4x the ingestion time; ingestion
    # happens once, centrally, on a fast machine.
    rag_embedding_model: str = "bge-m3"
    # Must match the model above. Baked into the vec0 table at creation, so
    # changing either means re-embedding -- which is now a background job
    # rather than a redistribution, because chunks.text is already on device.
    rag_embedding_dims: int = 1024
    # How many chunks are retrieved and pasted into the prompt.
    #
    # MEASURED 2026-09-04 with the per-turn metrics, and the number this whole
    # setting turns on: prefill is linear at ~15ms per prompt token, and one
    # passage is ~285 tokens. **Every retrieved passage costs ~4.3s** of prefill
    # before the student hears a word. That is the real latency cost of RAG --
    # not the search, which is 3-8ms for the vector scan and 10-30ms for FTS5,
    # both dwarfed by the 89ms query embedding and all of it 0.6% of a turn.
    #
    # Interleaved on four novel questions per arm (loaded dev box, so read the
    # ratios and not the absolutes):
    #
    #        prompt      prefill    turn    groundedness
    #   k=4  1404 tok     21.0s    29.8s       0.70
    #   k=2   841 tok     11.9s    20.0s       0.57
    #   none  270 tok      3.4s     7.5s        --
    #
    # k=2 gives back 9.1s of prefill and a third of the turn, but drops 0.13 of
    # groundedness -- on some questions the passage that actually answers sits
    # at rank 3 or 4. 3 is the middle: ~4.3s cheaper than 4, and it still
    # reaches a rank-3 answer. Re-check with scripts/evaluate_retrieval.py
    # --report after changing this; precision@k and the k in the harness both
    # move with it.
    rag_top_k: int = 3
    # Candidates pulled from each leg before fusion. Fifty each is plenty at
    # curriculum size -- the flat scan is ~8ms and the cost is all in prefill.
    rag_candidates: int = 50
    # Reciprocal Rank Fusion damping. Rank-based, so BM25 scores and cosine
    # distances never need a common scale.
    rag_rrf_k: int = 60

    # --- The relevance gate ---
    # There is no single rag_max_distance any more, and there cannot be: the
    # distance scale shifts with the query language. A correct hit sits at 0.21
    # for an English question and 0.51 for a Hindi question against the same
    # English page, so one constant either discards every correct Hindi result
    # or admits every wrong English one.
    #
    # Relative gate: keep hits within this much of the best hit. Normalises the
    # language offset away, because every candidate for one query shares it.
    rag_relative_margin: float = 0.12
    # Per-query-language ceilings: reject everything when even the best hit is
    # this far out. This is the mechanism that lets the tutor decline.
    #
    # MEASURED against scripts/golden_set.json on the Class 6 Science corpus
    # with scripts/evaluate_retrieval.py --calibrate. Each ceiling is the
    # midpoint between the worst CORRECT-chunk distance and the best off-topic
    # one -- correct-chunk, not best-hit, because those differ exactly where
    # ranking is poor and that is where a ceiling matters.
    #
    #              correct chunk (min/med/max)   off-topic min   ceiling
    #   en            0.286 / 0.329 / 0.439          0.575         0.51
    #   hi            0.313 / 0.430 / 0.536          0.627         0.58
    #   mr            0.331 / 0.438 / 0.556          0.627         0.59
    #   romanized     0.649 / 0.672 / 0.717          0.661       OVERLAP
    #
    # The decision record's starting values (0.45 / 0.62 / 0.62) came from a
    # different corpus. 0.45 sat 0.011 above the worst correct English hit --
    # one noisier book from being wrong.
    rag_ceiling_en: float = 0.51
    rag_ceiling_hi: float = 0.58
    rag_ceiling_mr: float = 0.59
    # Romanized Hindi/Marathi ("gharshan bal kya hai"): DELIBERATELY BELOW THE
    # NOISE FLOOR, so these questions retrieve nothing and the tutor answers
    # unaided.
    #
    # This is not a tuning choice, it is what the measurement forces. bge-m3
    # has no usable signal for Latin-script Indic against this corpus: the
    # correct chunk sits at 0.649-0.717 while off-topic passages sit at 0.661,
    # so the right answer is FARTHER AWAY than a wrong one. Half the romanized
    # golden questions do not retrieve their answer in the top fifty at all,
    # and the passages that do rank first are front matter -- the production
    # officer's name scored 0.6188 for "chumbak ke dhruv kya hote hain".
    #
    # That is the same signature nomic-embed-text showed on Devanagari Hindi,
    # and it fails the same way: silently, with a confident citation. A
    # ceiling that admits these admits noise with a chapter and page attached,
    # which is the precise failure the gate exists to prevent.
    #
    # 0.0 means no distance can ever clear it: retrieval is OFF for this
    # bucket. That is deliberate rather than a tuned number, because the
    # ordering is inverted and no threshold can separate the two populations.
    # Measured noise floor: "saral yantra kya hote hain" returns a passage
    # about Songardh in Gujarat at 0.558, while its correct chunk sits at
    # 0.677. A ceiling picked to exclude today's noise would be fitted to this
    # corpus's front matter and would start admitting garbage on the next book.
    #
    # The fix is transliteration to Devanagari before embedding, not a
    # threshold -- romanized text routed through the Devanagari path would
    # inherit hi's working retrieval. Until that lands, abstaining is the
    # honest behaviour: the student gets a model answer instead of a confident
    # citation to a page about galaxies. Re-check with
    # scripts/evaluate_retrieval.py --check after any change here.
    rag_ceiling_romanized: float = 0.0

    # Token budget for the assembled context block. Tokens, not characters:
    # a 2,000-character Devanagari passage measures 1,442 tokens against 578
    # for the same characters of English, so four of them are 5,925 tokens of
    # context alone. A character budget fits four English passages and
    # overruns on four Hindi ones, after which Ollama truncates from the front
    # and drops the system prompt without raising anything.
    #
    # Derived from num_ctx rather than guessed:
    #   6144 num_ctx
    #   - 564 system prompt with no context (measured, Hindi persona)
    #   - 840 replayed history at max_history_messages
    #   - 200 max_tokens for the reply
    #   - 540 headroom, because the estimator errs low by design
    #   = 4000
    # Worst measured case (4 x 2,000-char Devanagari) fills it at k=2 and
    # totals 4,613 of 6,144. Passages are added whole; k falls before a
    # passage is cut.
    rag_context_token_budget: int = 4000
    # Chunk bounds, in CHARACTERS -- splitting is a text operation. These are
    # not a context budget: 2,000 characters of English is about 500 tokens and
    # 2,000 characters of Hindi can be three times that, which is why the
    # prompt is assembled against tokens instead (rag_context_token_budget).
    #
    # Three numbers rather than one. Paragraph packing aims at `target`; a
    # single paragraph longer than `max` is split on sentences; anything under
    # `min` is dropped. The gap between target and max is what lets a section
    # run slightly long to stay whole rather than being cut at character 1,201.
    rag_chunk_target_chars: int = 1200
    rag_chunk_max_chars: int = 2000
    # The floor is low on purpose. A one-line definition ("Xylem: the tissue
    # that carries water.") is exactly what a definition question wants, and a
    # higher floor drops it silently.
    rag_chunk_min_chars: int = 40
    # Overlap carried between neighbours so a definition split across a
    # boundary survives in at least one of them. Zero at a heading -- see
    # chunking.flush().
    rag_chunk_overlap_chars: int = 180
    # Chunks embedded per Ollama call during ingestion.
    rag_embed_batch_size: int = 16
    # Upload ceiling for a single PDF.
    rag_max_upload_mb: int = 80

    # --- CORS -------------------------------------------------------------
    # Comma-separated list. "*" is fine for a local POC.
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> List[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
