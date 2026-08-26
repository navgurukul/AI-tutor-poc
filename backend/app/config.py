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
