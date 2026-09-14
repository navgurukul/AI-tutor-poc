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
    # CPU threads Ollama decodes with. 0 = omit the option and let Ollama
    # auto-detect, which is the right default on unknown hardware.
    #
    # Set it to the PHYSICAL core count, not the thread count: oversubscribing
    # hyperthreads makes the cores contend and costs ~10-20% on decode. The
    # 2026-09-07 target box is an i7-6600U -- 2 physical cores / 4 threads, 15 W
    # Skylake -- so 2, not 4.
    #
    # `OLLAMA_NUM_THREAD` sat in .env for weeks doing nothing: there was no field
    # here, extra="ignore" dropped it, and it is not a variable the Ollama daemon
    # reads either. Thread count was left entirely to auto-detection.
    ollama_num_thread: int = 0
    ollama_timeout_seconds: float = 180.0
    # Re-read each answer in the background as soon as it is written, so the
    # next question does not pay for it. Ollama 0.34 runs gemma2 on llama.cpp's
    # server, which for a sliding-window model can only resume from a
    # checkpoint -- and saves one only at the end of each PROMPT, before the
    # reply. Every follow-up therefore re-read the previous answer (65-129
    # tokens, 2.5-5 s) while the student waited. Measured 2026-09-10, same
    # prompt, 4 rounds: next-turn prefill 5.3-6.0 s without, 2.5-2.6 s with.
    # The prime itself (~3.5 s) runs while the answer is being spoken.
    ollama_reprime_after_reply: bool = True
    ollama_connect_timeout_seconds: float = 5.0

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
    # Devanagari costs 2-4x more tokens per word than English, so the same answer
    # needs a bigger token cap to land its final sentence instead of being cut
    # off mid-word. Kept as its own setting rather than a multiplier because the
    # two are tuned against different failure modes: English against padding,
    # Devanagari against truncation.
    #
    # This field is new as of 2026-09-07. `MAX_TOKENS_NON_ENGLISH` had been in
    # .env (and in the decision record) for weeks with no field behind it, so
    # pydantic's extra="ignore" silently dropped it and non-English turns used
    # `max_tokens` the whole time.
    max_tokens_non_english: int = 240
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

    # --- Offline speech-to-text -------------------------------------------
    # Two engines behind /api/stt, picked per language:
    #   Hindi / Marathi -> sherpa-onnx + AI4Bharat IndicConformer-600M (CTC),
    #     emits the correct native script. fp32 `model.onnx` (~470 MB) by
    #     default; int8 roughly doubles the WER (Hindi ~0.16 -> ~0.30).
    #   English         -> sherpa-onnx + Whisper base.en (int8, ~145 MB) - solid
    #     on Indian-accented English, so English STT is also fully offline. The
    #     folder auto-detects Whisper vs Moonshine by its files, so pointing
    #     STT_ENGLISH_DIR at a Moonshine folder still works.
    # Each folder (relative paths resolve against apps/backend/) is placed by
    # scripts/setup.ps1. Missing files -> /api/stt reports that language "not
    # ready" instead of breaking the app.
    stt_indic_dir: str = "models/indicconformer"
    stt_indic_file: str = "model.onnx"
    stt_english_dir: str = "models/stt/sherpa-onnx-whisper-base.en"
    # Decode is CPU-bound and nothing else runs during it (the LLM turn hasn't
    # started yet), so give it more threads. Lower it if the box has <4 cores.
    stt_num_threads: int = 4

    # --- Offline text-to-speech -------------------------------------------
    # sherpa-onnx + one Piper VITS voice per language (no extra dependency —
    # sherpa is already installed for STT). Under this directory each language
    # has a folder named after it (english/, hindi/, marathi/) holding
    # <voice>.onnx + tokens.txt, beside one shared espeak-ng-data/. Placed by
    # scripts/setup.ps1; adding a language is dropping in a folder.
    # Which language's speech models to load at boot. Only one is warmed: a
    # session uses a single language, and warming all of them tripled the boot
    # work and the resident memory for two nobody touches. The others still load
    # on their first use — the frontend asks /api/stt and /api/tts whether a
    # language is ready when it mounts, which triggers the load before the
    # student has finished speaking. Set empty to warm nothing.
    warm_language: str = "English"

    tts_model_dir: str = "models/tts"
    # Synthesis runs while the model is still generating the rest of the answer,
    # so it stays below stt_num_threads — STT decodes while Ollama is idle.
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
    # keep_alive for the *query* embed only (ingestion keeps ollama_keep_alive).
    # At runtime bge-m3 only embeds the question (~10 words, ~1.1s); the corpus
    # vectors are already in the DB, so in principle it need not stay resident
    # through the ~30s generation turn that follows.
    #
    # MEASURED 2026-09-07 on the 8 GB target, and it does NOT pay off here:
    #   "0"   -> warm-up wall 23.5s -> 10.7s, prefill -5s, BUT a cold 1.2 GB
    #            reload every turn cost +7.5s on retrieval. Net zero.
    #   "30s" -> turns are 40-80s apart so it never spans two, i.e. same reload
    #            every turn, and the reload degraded to 10-20s as the box
    #            thrashed. Turn total went UP (to 80s). Strictly worse.
    # So: keep it pinned and eat the ~5s paging tax on prefill -- cheaper than
    # any reload this disk can do. Revisit ("0" or "20s") only on a box with
    # headroom, or once the generator moves off-box (LAN Ollama host).
    rag_embed_query_keep_alive: str = "-1"
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
    # Re-measured 2026-09-10 on clean text (PyMuPDF + doubled-matra repair),
    # Class 6 Hindi, bge-m3: 12 answerable questions scored 0.27-0.47 (one
    # bare-title outlier at 0.532), 10 off-syllabus ones 0.53-0.61. The old
    # 0.58 was tuned on mis-decoded text and let 4 of the 10 off-syllabus
    # questions through with a textbook citation; 0.50 sits in the gap.
    rag_ceiling_hi: float = 0.50
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
    # Per-passage cap, applied AFTER ranking and BEFORE the prompt is built.
    # 0 disables trimming and ships whole chunks, which is what shipped before
    # 2026-09-09.
    #
    # A chunk is 1,200 characters because that is the size that *embeds* well --
    # the vector needs surrounding context to rank correctly. The model does not
    # need all of it to answer, and on this CPU every prompt token is re-read
    # before the student hears anything: measured 2026-09-09, prompt tokens cost
    # ~22ms each and three passages ran 538-617 tokens, i.e. 12-14s of the wait.
    #
    # 90 tokens is roughly the definition plus one example -- about half what a
    # passage carries now. Sentences are picked by overlap with the question
    # (see trim_passage), so this should raise precision as well as cut tokens:
    # the same session that motivated this returned a groundwater passage for a
    # question about "भूमिका" and the model recited it.
    #
    # Raise it if answers start missing detail the passage clearly had; set 0
    # to rule the trimmer out while chasing a retrieval bug.
    #
    # OFF (0) as of 2026-09-09, after it silently broke an answer.
    #
    # Asked "संज्ञा और उसके भेदों का विवरण करें", the trimmer kept
    #     "संज्ञा के तीन मुख्य भेद माने जाते हैं।"   (there are three types)
    # and dropped
    #     "व्यक्तिवाचक ... जातिवाचक ... भाववाचक ..."  (what the three types ARE)
    # so the model was told a list existed, not what was in it, and invented
    # "प्राधिकारिक, प्रमाणिक और अनोखे". The same question answered correctly
    # before trimming was switched on.
    #
    # The cause is structural, not a bad threshold: sentences are scored by
    # overlap with the question, and a topic sentence repeats the question's
    # words ("संज्ञा", "भेद") while the sentences carrying the answer use
    # different ones. Lexical scoring therefore prefers headlines and discards
    # substance -- exactly the silent truncation fit_to_budget refuses to do.
    #
    # It also never paid here: this corpus chunks at 97-349 characters, so a
    # "passage" is already about one cap's worth. Trimming is only worth
    # reopening for 1000+ character chunks, and then only if the scorer keeps
    # the sentences AROUND the best match rather than the best match alone.
    # RE-ENABLED 2026-09-10 at 110, with a DIFFERENT algorithm.
    #
    # The version that broke an answer selected the best-MATCHING sentences and
    # dropped the rest. It now keeps the HEAD in order, which has neither
    # failure mode -- see trim_passage.
    #
    # 110 because retrieved passages dominate the cost of a turn: they are
    # always NEW tokens, and a new token costs ~50ms against ~2ms for a cached
    # one. Measured the same day, a single passage was arriving at 341-375
    # estimated tokens -- roughly 14s of a 22s prefill, for one chunk. The
    # median chunk in this corpus is 125 estimated tokens, so this barely
    # touches a typical passage and cuts only the outliers (largest: 1009).
    #
    # Raise it if answers start missing detail the passage clearly had; 0 turns
    # trimming off entirely.
    rag_passage_token_cap: int = 110
    # Pin the WHOLE corpus into the system prompt instead of retrieving per
    # question, whenever it fits in this many tokens. 0 disables pinning.
    #
    # This is a latency setting, and it is the largest one measured on this box.
    # Ollama reuses a cached KV prefix only against the request that immediately
    # preceded it -- not against any older one that happens to share a prefix.
    # Per-question retrieval therefore changes the prompt every turn, consecutive
    # prompts diverge right after the persona, and the 568-token persona is
    # re-prefilled every single question. Measured 2026-09-09:
    #
    #     per-question retrieval : 15-26s of prefill, every turn
    #     pinned corpus          : 1.6-3.1s (turn 1 / 2 / 3)
    #
    # Same model, same hardware. The cost is a one-time ~47s prime at startup,
    # which the background warm-up absorbs before any student asks anything.
    #
    # Only honest while the corpus is small: over budget, this falls back to
    # per-question retrieval rather than truncating. The live corpus is ~1105
    # estimated tokens (7 chunks), so 1500 leaves room without letting a real
    # textbook through. A full book needs the pinned block scoped to a chapter
    # instead -- same mechanism, different unit.
    #
    # Two settings must move with it, or the cache is thrown away anyway:
    #   NUM_CTX               big enough for persona + corpus + a session of history
    #   MAX_HISTORY_MESSAGES  large enough not to SLIDE mid-session; dropping the
    #                         oldest message rewrites the prefix and loses the cache
    rag_pin_corpus_max_tokens: int = 1500
    # Skip pasting a passage this session has already been given.
    #
    # Excerpts live inside the turn they belong to (tutor.build_turn_message),
    # so a chunk retrieved earlier is still in the conversation and still in
    # Ollama's KV cache. Sending it again costs ~110 NEW tokens -- about 5.5s at
    # the measured ~50ms per new token -- to repeat something the model can
    # already read a few lines up.
    #
    # Measured 2026-09-10, the cost of a turn is:
    #     prefill ~= (new tokens x ~50ms) + (total tokens x ~2ms)
    # so what a turn adds matters far more than how long the prompt is. With
    # dedup on, a follow-up on the same topic adds nothing and runs ~5s, while a
    # new topic adds one passage and runs ~9s -- fast exactly where it is earned,
    # and never ungrounded where it is not.
    #
    # Citations and groundedness still see every hit; only the text pasted into
    # this turn shrinks. Set false to paste the passages on every turn.
    rag_dedup_context: bool = True
    # A short follow-up that refers back ("इसका एक उदाहरण दीजिए", "explain this
    # again") keeps the previous passage instead of searching on its own words.
    # Searched alone, "इसका एक उदाहरण दीजिए" matched an unrelated passage on
    # 2026-09-10 and the answer was nonsense (groundedness 0.00). Kept, the
    # passage is already in the conversation, so the turn adds no new tokens.
    rag_followup_reuse: bool = True
    # The reply rules (plain sentences, word budget, no closing question, reply
    # language) live at the END of the cached persona, and each turn repeats only
    # a short reminder. Sent with every turn they are new tokens every time: 56
    # real tokens on a Hindi textbook turn, 47 in English, against 10 and 7 for
    # the reminder -- about 1.5-1.7 s less before the first word at ~38 ms per
    # new token. Quality check 2026-09-11 (7 questions, Hindi + English, same
    # seed): key fact 7/7 against 5/7 with the rules on every turn, all replies
    # in the right language, none talking about the text. Moving the rules with
    # NO reminder was worse -- answers ran to 118-159 words -- which is why the
    # reminder stays. Set false to put the full rules back on every turn.
    tutor_rules_in_persona: bool = True
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
