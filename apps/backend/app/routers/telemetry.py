"""Where the frontend posts what the student actually experienced.

The backend can time itself, but it cannot see the half that matters most: how
long until words appeared on screen, and how long until the voice was audible.
Only the browser knows that, and a browser cannot write to the log directory --
so it sends the numbers here and the backend appends them.

Durations only. No question, no answer, no identity beyond the session id the
backend itself issued.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter

from app.services import turnlog

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])
logger = logging.getLogger(__name__)

# Anything else in the body is dropped rather than trusted into a CSV.
_ALLOWED = {
    "turn_id",
    "session_id",
    "ttft_ms",
    "first_sentence_ms",
    "first_audio_ms",
    "full_reply_ms",
    "fully_spoken_ms",
    "answer_chars",
}


def _clean(payload: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for key in _ALLOWED:
        value = payload.get(key)
        if value is None:
            continue
        if key in ("turn_id", "session_id"):
            # Ids go into a CSV cell; keep them to what the backend issues.
            text = str(value)[:64]
            row[key] = "".join(c for c in text if c.isalnum() or c in "-_")
        else:
            try:
                row[key] = int(value)
            except (TypeError, ValueError):
                continue
    return row


@router.post("/turn", status_code=204, summary="Record client-side turn timings")
async def record_turn(payload: Dict[str, Any]) -> None:
    """Fire-and-forget: the tutor must never wait on, or fail because of, a log."""
    try:
        row = _clean(payload)
        if row.get("turn_id"):
            row["ts_utc"] = turnlog.now_utc()
            turnlog.log_frontend_turn(row)
    except Exception:  # noqa: BLE001 - telemetry cannot break a lesson
        logger.debug("Dropped a malformed telemetry row", exc_info=True)
