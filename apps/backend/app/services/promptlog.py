"""Raw LLM prompt/response log, as JSON Lines, for seeing exactly what a turn sent.

turnlog.py deliberately never carries question or answer text. This is the
opposite: the full `messages` array Ollama received and the full reply it gave
back, plus the raw character length of that array's content (`prompt_chars`),
one JSON object per line. Off by default (app.config.settings.
prompt_log_enabled) -- turn it on with PROMPT_LOG_ENABLED=true to inspect a
real prompt.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.turnlog import _logs_dir

logger = logging.getLogger(__name__)

_lock = threading.Lock()

FILENAME = "prompts.jsonl"


def log_prompt(
    messages: List[Dict[str, str]],
    reply: Optional[str],
    model: str,
    turn_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Append one line with the exact prompt sent and the reply received."""
    if not settings.prompt_log_enabled:
        return
    # Raw character count of what was actually sent, not a token estimate --
    # summed across every message's content, in the same order as `messages`.
    prompt_chars = sum(len(m.get("content") or "") for m in messages)
    row: Dict[str, Any] = {
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "turn_id": turn_id,
        "model": model,
        "messages": messages,
        "prompt_chars": prompt_chars,
        "reply": reply,
    }
    if extra:
        row.update(extra)
    try:
        directory = _logs_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / FILENAME
        with _lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        # A debug log must never be the reason a lesson stops.
        logger.warning("Could not write %s: %s", FILENAME, exc)
