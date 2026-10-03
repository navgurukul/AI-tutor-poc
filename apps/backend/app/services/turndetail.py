"""Full per-turn record, for judging a turn by reading it.

turnlog.py keeps shapes and durations only, because those CSVs travel off
classroom laptops. This is the other half, for a developer or an evaluation
session: for one turn, the question, every passage retrieval returned (and whether the
budget cut it before the prompt), the exact messages and options sent to Ollama,
Ollama's own timings, and the answer.

Two views of the same record:

  logs/turns.jsonl   one JSON object per line, append-only, `jq`-friendly:
                       jq -r '.prompt.messages[] | "--- \\(.role)\\n\\(.content)"' turns.jsonl
  recent()/get()     the last RECENT_LIMIT turns in memory, which is what
                     GET /api/eval/turns and the frontend panel read

Off in a packaged build unless TURN_DETAIL_LOG=true (config.turn_detail_enabled).
"""

from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from app.config import settings
from app.services.turnlog import _logs_dir

logger = logging.getLogger(__name__)

RECENT_LIMIT = 200
_lock = threading.Lock()
_recent: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()


def enabled() -> bool:
    return settings.turn_detail_enabled


def record(turn: Dict[str, Any]) -> None:
    """Keep the turn in memory and append it to turns.jsonl. Never raises."""
    if not enabled():
        return
    turn_id = str(turn.get("turn_id") or "")
    with _lock:
        if turn_id:
            _recent[turn_id] = turn
            while len(_recent) > RECENT_LIMIT:
                _recent.popitem(last=False)
        try:
            directory = _logs_dir()
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / "turns.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(turn, ensure_ascii=False) + "\n")
        except OSError as exc:
            # A log must never be the reason a lesson stops.
            logger.warning("Could not write turns.jsonl: %s", exc)


def get(turn_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _recent.get(turn_id)


def recent(limit: int = 50) -> List[Dict[str, Any]]:
    """Newest first."""
    with _lock:
        return list(reversed(list(_recent.values())))[: max(1, limit)]


def retrieved_chunks(hits, shown) -> List[Dict[str, Any]]:
    """Every retrieved passage, marked with what reached the prompt.

    `hits` is what the search returned; `shown` is the same passages after
    shortening and the character budget. A hit absent from `shown` was
    retrieved but never read by the model.
    """
    sent = {h.chunk_id: h.text for h in shown}
    rows = []
    for rank, hit in enumerate(hits, start=1):
        text = sent.get(hit.chunk_id)
        rows.append(
            {
                "rank": rank,
                "chunk_id": hit.chunk_id,
                "title": hit.document_title,
                "heading": hit.heading,
                "page_start": hit.page_start,
                "page_end": hit.page_end,
                "grade": hit.grade,
                "subject": hit.subject,
                "distance": round(hit.distance, 4),
                "chars_retrieved": len(hit.text),
                "chars_sent": len(text) if text is not None else 0,
                "sent": text is not None,
                "excerpt": text if text is not None else None,
                "retrieved_text": hit.text,
            }
        )
    return rows


def hybrid_chunks(chunks) -> List[Dict[str, Any]]:
    """Turn-log rows for rag.hybrid passages, same keys as retrieved_chunks.

    There is no budget cut to report: the engine budgets the merged passages
    itself, so every chunk here was sent. `score` is the fused RRF score;
    `distance` is the cosine distance, None on a passage the dense search did
    not return itself (lexical-only, neighbour or whole-section).
    """
    from app.services.rag import hybrid

    rows = []
    for rank, chunk in enumerate(chunks, start=1):
        rows.append(
            {
                "rank": rank,
                "chunk_id": chunk.id,
                "title": hybrid.source_name(chunk),
                "heading": hybrid.breadcrumb(chunk),
                "page_start": 0,
                "page_end": 0,
                "grade": None,
                "subject": None,
                "distance": round(chunk.distance, 4) if chunk.distance is not None else None,
                "score": round(chunk.score, 5),
                "matched_via": chunk.matched_via,
                "seq": chunk.seq,
                "chars_retrieved": len(chunk.text),
                "chars_sent": len(chunk.text),
                "sent": True,
                "excerpt": chunk.text,
                "retrieved_text": chunk.text,
            }
        )
    return rows
