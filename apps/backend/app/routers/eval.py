"""Read-only evaluation endpoints: the golden set and the per-turn record.

The golden set is the same 20 questions AFE-Learning-App benchmarks with
(docs/groundedness/afe-golden.json, copied from its benchmarks/golden), so the
two apps can be compared question by question. The turn record is what
services/turndetail.py keeps: retrieval, the prompt sent, timings, the answer.

Both are development tools. They return question and answer text, so a packaged
build answers 404 unless TURN_DETAIL_LOG=true.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from app.services import turndetail

router = APIRouter(prefix="/api/eval", tags=["eval"])

GOLDEN_PATH = Path(__file__).resolve().parents[4] / "docs" / "groundedness" / "afe-golden.json"


def _require_enabled() -> None:
    if not turndetail.enabled():
        raise HTTPException(
            status_code=404,
            detail="Turn detail logging is off. Set TURN_DETAIL_LOG=true to enable it.",
        )


@router.get("/golden", summary="The golden question set")
async def golden() -> Dict[str, Any]:
    _require_enabled()
    try:
        return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    except OSError:
        raise HTTPException(status_code=404, detail="Golden set not found: {}".format(GOLDEN_PATH))


@router.get("/turns", summary="Most recent turn records, newest first")
async def turns(limit: int = Query(50, ge=1, le=200)) -> List[Dict[str, Any]]:
    _require_enabled()
    return turndetail.recent(limit)


@router.get("/turns/{turn_id}", summary="One turn: retrieval, prompt, timings, answer")
async def turn(turn_id: str) -> Dict[str, Any]:
    _require_enabled()
    record = turndetail.get(turn_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No such turn in the recent window.")
    return record
