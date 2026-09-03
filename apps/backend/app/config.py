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
    # Smaller context = faster prompt processing on CPU. Enough for the system
    # prompt plus the trimmed history below.
    num_ctx: int = 3072

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
    # How many chunks are retrieved and pasted into the prompt. Each one costs
    # prefill time on a CPU-bound model, which is the real latency cost of RAG
    # -- the search itself is under a millisecond.
    rag_top_k: int = 4
    # Cosine distance above which a hit is treated as irrelevant. Without it a
    # question the textbooks don't cover still drags in the four least-bad
    # chunks and invites the model to answer from them.
    #
    # Calibrated, not guessed: against a Class 9 Science chapter, questions the
    # text answers scored 0.12-0.34 and off-topic ones ("capital of France",
    # "bake bread") scored 0.50-0.58. 0.42 sits in the gap. Re-measure with
    # POST /api/library/search if you change the embedding model.
    rag_max_distance: float = 0.42
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
