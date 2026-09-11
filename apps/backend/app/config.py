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
    # Caps the tail of a slow turn. The persona already asks for under 200
    # words (~260 tokens); 800 only ever bought a runaway answer, and on a CPU
    # at ~9 chars/s the difference is minutes.
    max_tokens: int = 400
    # Kept well under the model's 32k window; keeps replies fast on CPU.
    num_ctx: int = 4096

    # --- Conversation memory ---------------------------------------------
    # What the model re-reads of the conversation. NOT what the student sees:
    # the full reply is streamed, stored and returned unchanged. These two were
    # one string until they were measured, and that cost 3.9s a turn.
    #
    # The history window used to be a flat "last N messages", which meant the
    # previous *answer* came back in full. At 851 characters that is ~218
    # tokens, and at 18.2ms per prompt token it bought ~3.9s of prefill on
    # every turn after the first -- so answer length was charged twice, once to
    # generate and again to re-read. Measured on target 2026-09-10: turn 1 at
    # 5.6s to first token, turn 5 at 9.2s, rising monotonically with the length
    # of the preceding answer.
    #
    # What is replayed now, and why each part earns its tokens:
    #
    #   the previous question   ~6 tok   what a pronoun binds to. "Why does it
    #                                    get bigger?" resolves against "What is
    #                                    a shadow?" as well as against any
    #                                    answer, and costs a twentieth as much.
    #   the closing nudge      ~28 tok   socratic style only. Every reply ends
    #                                    by inviting the student to think, so
    #                                    their next message is often a REPLY to
    #                                    that -- "because it would go pale?".
    #                                    Without it the model cannot see the
    #                                    question it asked, and a perfectly good
    #                                    answer arrives as a non-sequitur.
    #   the current question    ~6 tok   always present.
    #
    # Everything else in the previous answer -- the worked example, the
    # elaboration -- is never referred back to, and is dropped.
    #
    # One is enough: the immediate antecedent is what pronouns bind to, and a
    # second question buys ~6 tokens of context for ~0.1s. Raising this is
    # cheap if follow-ups start losing the thread.
    history_questions: int = 1
    # Cap on the retained closing sentence, so a model that ends with a
    # paragraph instead of a line cannot reintroduce the cost this removed.
    history_nudge_max_chars: int = 200
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
    # Now 2, measured on the target: dropping the third excerpt took prefill
    # from 6.5s to 3.7s and first token from 6.3s to 4.1s. RAG_TOP_K overrides.
    rag_top_k: int = 2
    # Hard ceiling on retrieved text, applied after ranking. rag_top_k alone
    # does not bound latency: prefill costs ~25-30ms per token on the target
    # laptop, and four chunks measured anywhere from 1,178 to 3,376 characters
    # depending on the question -- 10.7s vs 28.6s to first token for the same
    # k. Budgeting characters makes the wait predictable instead of a lottery
    # on which passages happen to be long. Chunks are dropped from the end, so
    # the best-ranked excerpt is always kept.
    #
    # Measured on the target laptop: base prompt with no excerpts reaches first
    # token in 3.3s; 1,178 characters of excerpt takes 10.7s; 3,376 takes
    # 28.6s. Roughly 20-27ms per token of prefill, linear.
    #
    # Now at 1200. Once the excerpts moved out of the system message and the
    # history window came down to 2, this became the largest remaining piece of
    # the prompt -- and the only piece that changes every turn, so it is the
    # part no amount of caching can ever make free. Raise it if a site would
    # rather wait for better grounding; every 100 characters is roughly half a
    # second. RAG_CONTEXT_MAX_CHARS overrides.
    rag_context_max_chars: int = 1200
    # Cosine distance above which a hit is treated as irrelevant. Without it a
    # question the textbooks don't cover still drags in the four least-bad
    # chunks and invites the model to answer from them.
    #
    # Calibrated, not guessed: against a Class 9 Science chapter, questions the
    # text answers scored 0.12-0.34 and off-topic ones ("capital of France",
    # "bake bread") scored 0.50-0.58. 0.42 sits in the gap. Re-measure with
    # POST /api/library/search if you change the embedding model.
    rag_max_distance: float = 0.42
    # A follow-up with a dangling pronoun ("how can we reduce it?") is searched
    # with the previous question in front of it, because on its own it embeds
    # to nothing and retrieval wanders into other chapters -- 6 of 10 follow-ups
    # did in exp004. Questions without one are searched exactly as typed; see
    # app.services.rag.followup for why this is conditional. Only the search
    # changes, never the prompt. RAG_CARRY_FOLLOWUPS=0 turns it off, for an
    # A/B run of the benchmark.
    rag_carry_followups: bool = True
    # Characters per chunk, and the overlap carried between neighbours so a
    # definition split across a boundary survives in at least one of them.
    rag_chunk_chars: int = 1200
    rag_chunk_overlap_chars: int = 180
    # Chunks embedded per Ollama call during ingestion.
    rag_embed_batch_size: int = 16
    # Upload ceiling for a single PDF.
    rag_max_upload_mb: int = 80

    # --- Latency logging --------------------------------------------------
    # Per-turn CSVs in the log directory, for working out where a slow device
    # is spending its time. Shapes and durations only -- never question or
    # answer text, because these files get copied off classroom laptops.
    turn_log_enabled: bool = True

    # --- Serving / packaging ---------------------------------------------
    # Loopback by default. A packaged device build must never bind 0.0.0.0:
    # the library upload and delete routes have no auth, so a wildcard bind
    # publishes them to every peer on the school network.
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    # Directory of built frontend assets to serve at "/". Empty disables the
    # mount, which is what a developer running Vite on its own port wants. The
    # packaged launcher points this at the installed web/ directory, making the
    # product same-origin and removing the need for Node at runtime.
    web_dir: str = ""
    # Set by the packaged launcher: turns off the interactive API docs and
    # enables the loopback request guards.
    packaged: bool = False

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
