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
    # A Socratic answer is 2-3 sentences; a low cap keeps CPU generation short.
    # Hindi costs 2-4x more tokens per word than English, so this matters most
    # there. Raise it if answers get cut off mid-sentence.
    max_tokens: int = 220
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
    stt_num_threads: int = 2

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
