"""One JSON line per pipeline event -- stt, retrieval, llm, tts -- appended to
its OWN file per stage (logs/stt.jsonl, logs/retrieval.jsonl, ...), separate
from the console log `main.py` sets up with `logging.basicConfig`. Each stage
also gets a logs/{event}.pretty.json -- a real, indented JSON array of its
most recent entries, auto-rewritten on every event -- for reading straight in
an editor instead of through `jq`; see `turn_log_pretty`'s own comment in
config.py for what that costs and how to turn just it off.

One file per stage rather than one shared file: `tail -f logs/stt.jsonl` then
shows only STT calls, growing forever (until it rotates by size) instead of
being interleaved with retrieval/LLM/TTS lines you'd have to filter out.

The point is to be able to see, per stage, what actually happened -- not just
how long it took: for STT the audio shape and the transcribed text, for
retrieval the chunks considered and which of those actually got pasted into
the prompt, for the LLM the final prompt and reply, for TTS the text spoken.
The per-turn summary line in `app/services/rag/metrics.py` (`format_turn`)
already reports *timings*; this reports *content*, at finer grain, into files
meant to be read with `jq` rather than scrolled past in a terminal.

Usage: each stage calls `log_event("stt", **fields)` (etc.) at the point it
already has the relevant values in scope. `configure()` runs once at startup
(see `main.py`); calling `log_event` before that, or with logging disabled, is
a safe no-op -- a logging bug or a missing directory must never break a turn.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.config import settings

# apps/backend/ -- relative turn_log_dir resolves against this, same as the
# model/data paths in config.py.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_enabled = False
_dir: Path = _BACKEND_ROOT  # overwritten by configure(); harmless default
# Guards first-time handler creation per event type -- see _logger_for. Not
# needed for the writes themselves: each stdlib Logger/Handler is already
# thread-safe for concurrent .info() calls on its own.
_setup_lock = Lock()


def configure() -> None:
    """Resolve and create the log directory. Called once from `main.py` at
    startup; safe to call again (a no-op after the first time)."""
    global _enabled, _dir
    if _enabled or not settings.turn_log_enabled:
        return
    d = Path(settings.turn_log_dir)
    if not d.is_absolute():
        d = _BACKEND_ROOT / d
    d.mkdir(parents=True, exist_ok=True)
    _dir = d
    _enabled = True


def _logger_for(event: str) -> logging.Logger:
    """The logger for one event type, e.g. "stt" -> logs/stt.jsonl.

    Lazily attaches its rotating file handler on first use, then reuses the
    same Logger object every time after (`logging.getLogger` already does
    that by name) -- so every call for the same stage keeps appending to the
    same file rather than opening a new one.
    """
    logger = logging.getLogger("ai-tutor.turnlog.{}".format(event))
    if logger.handlers:
        return logger
    with _setup_lock:
        if logger.handlers:  # another thread set it up while we waited
            return logger
        logger.propagate = False  # keep these lines out of backend.out.log
        logger.setLevel(logging.INFO)
        handler = logging.handlers.RotatingFileHandler(
            _dir / "{}.jsonl".format(event),
            maxBytes=settings.turn_log_max_bytes,
            backupCount=settings.turn_log_backup_count,
            encoding="utf-8",
        )
        # No timestamp/level prefix from the formatter -- log_event already
        # puts a `ts` field in the JSON payload, and the message IS the line.
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def _append_pretty(event: str, payload: dict) -> None:
    """Keep logs/{event}.pretty.json as a real JSON array of the most recent
    `turn_log_pretty_max_entries` events for this stage, indent=2.

    There is no cheap append for a JSON array -- this reads the whole file,
    adds one entry, drops the oldest past the cap, and rewrites it. See the
    `turn_log_pretty` setting's own comment for why that cost is bounded (the
    cap) but not free, and how to turn just this part off.
    """
    path = _dir / "{}.pretty.json".format(event)
    with _setup_lock:  # same lock as handler setup -- just needs to be A lock
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                entries = []
        except (FileNotFoundError, json.JSONDecodeError):
            # Missing (first event of this type) or a prior write was cut off
            # mid-file -- either way, start a fresh array rather than fail.
            entries = []
        entries.append(payload)
        cap = settings.turn_log_pretty_max_entries
        if cap > 0 and len(entries) > cap:
            entries = entries[-cap:]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False, default=str)


def log_event(event: str, **fields: Any) -> None:
    """Append one JSON line to logs/{event}.jsonl:
    `{"ts": ..., "event": event, **fields}`. Also keeps logs/{event}.pretty.json
    (a real, indented JSON array of the most recent entries) up to date, when
    `turn_log_pretty` is on -- see that setting's own comment for the cost.

    Never raises -- a failure here (disk full, bad value) costs one missing
    log line, not a broken turn. `event` is the stage name ("stt",
    "retrieval", "llm", "tts"); when the caller has a `session_id`, passing it
    in `fields` lets one turn be reassembled across files later.
    """
    if not _enabled:
        return
    payload = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    try:
        logger = _logger_for(event)
        logger.info(json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:  # noqa: BLE001 - logging must never break the caller
        logging.getLogger(__name__).warning(
            "turnlog: failed to write a %r event", event, exc_info=True
        )
    if settings.turn_log_pretty:
        try:
            _append_pretty(event, payload)
        except Exception:  # noqa: BLE001 - same contract as the line above
            logging.getLogger(__name__).warning(
                "turnlog: failed to update the pretty mirror for a %r event", event, exc_info=True
            )
