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
    ollama_model: str = "qwen2.5:1.5b"
    # A 1.5B model on CPU is quick, but a long answer plus a cold model load
    # can still take a while, so the read timeout is generous.
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
    max_tokens: int = 800
    # Kept well under the model's 32k window; keeps replies fast on CPU.
    num_ctx: int = 4096

    # --- Conversation memory ---------------------------------------------
    # Number of past messages (user + assistant) replayed to the model.
    max_history_messages: int = 20
    session_ttl_minutes: int = 180
    max_sessions: int = 500

    # --- Retrieval (RAG) ---------------------------------------------------
    # Textbook retrieval is additive: if the store can't be opened the tutor
    # still answers from the model alone, so a missing library is a degraded
    # feature rather than a broken app.
    rag_enabled: bool = True
    # Kept beside the backend package so it travels with the app; the whole
    # corpus (text + vectors) is one file that can be built centrally and
    # copied onto a device, which is the only sane option on a 15W laptop.
    rag_db_path: str = "data/library.db"
    rag_embedding_model: str = "nomic-embed-text"
    # Must match the model above. Baked into the vec0 table at creation, so
    # changing either means re-ingesting; the store refuses a silent mismatch.
    rag_embedding_dims: int = 768
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
    # Characters per chunk, and the overlap carried between neighbours so a
    # definition split across a boundary survives in at least one of them.
    rag_chunk_chars: int = 1200
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
