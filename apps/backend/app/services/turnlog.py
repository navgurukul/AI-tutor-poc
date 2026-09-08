"""Per-turn latency logs, as CSV, for offline analysis.

Every turn already produces timings; they were only ever visible in a console.
On a device that means nobody sees them, and across a fleet it means there is
no way to answer "is this laptop slow, or are they all like this".

Two files, because the two halves measure different things and neither is
complete on its own:

  turns-backend.csv   retrieval, prefill and generation, split out from
                      Ollama's own counters -- this is where the time goes
  turns-frontend.csv  what the student experienced: first token on screen,
                      first audio, and when speech actually finished

They join on turn_id. Written with a header on creation and appended
thereafter, so a run can be opened directly in a spreadsheet.

Deliberately NO question or answer text. These sit on a classroom laptop and
get copied around for analysis; a latency log has no business carrying what a
child asked. Only shapes and durations.
"""

from __future__ import annotations

import csv
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Sequence

from app.config import settings

logger = logging.getLogger(__name__)

BACKEND_FIELDS: Sequence[str] = (
    "ts_utc",
    "turn_id",
    "session_id",
    "question_chars",
    "history_msgs",
    "retrieval_ms",      # embedding + search + gate; the cheap part
    "sources",
    "context_chars",     # retrieved text put into the prompt, after budgeting
    "prompt_tokens",     # what Ollama actually had to prefill
    "prefill_ms",        # prompt_eval_duration -- usually most of the wait
    "ttft_ms",           # server-side first token
    "completion_tokens",
    "generation_ms",     # eval_duration
    "tokens_per_second",
    "load_ms",           # non-zero only when the model was not resident
    "total_ms",
    "answer_chars",
)

FRONTEND_FIELDS: Sequence[str] = (
    "ts_utc",
    "turn_id",
    "session_id",
    "ttft_ms",              # first token painted
    "first_sentence_ms",    # first sentence handed to the voice
    "first_audio_ms",       # first sound out of the speaker
    "full_reply_ms",        # last token painted
    "fully_spoken_ms",      # audio finished
    "answer_chars",
)

_lock = threading.Lock()


def _logs_dir() -> Path:
    """Where the launcher already keeps its logs, so everything lands together.

    AITUTOR_LOG_DIR is set by the packaged launcher; a developer run falls back
    to a logs/ beside the backend rather than writing into ProgramData.
    """
    configured = os.environ.get("AITUTOR_LOG_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "logs"


def _append(filename: str, fields: Sequence[str], row: Dict[str, Any]) -> None:
    if not settings.turn_log_enabled:
        return
    try:
        directory = _logs_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        # One lock for both files: turns are low-frequency and the cost of
        # serialising them is irrelevant next to a turn that takes seconds.
        with _lock:
            new = not path.exists()
            with path.open("a", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
                if new:
                    writer.writeheader()
                writer.writerow({k: row.get(k, "") for k in fields})
    except OSError as exc:
        # A latency log must never be the reason a lesson stops.
        logger.warning("Could not write %s: %s", filename, exc)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_backend_turn(row: Dict[str, Any]) -> None:
    _append("turns-backend.csv", BACKEND_FIELDS, row)


def log_frontend_turn(row: Dict[str, Any]) -> None:
    _append("turns-frontend.csv", FRONTEND_FIELDS, row)
