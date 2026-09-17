"""Live groundedness for questions from the gold set.

The chat stream flags a turn whose question is in docs/groundedness/evalset.json
and ends; the UI then asks here for the score. Kept out of the stream so a
student is never held up by the judge.
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from app.services import groundedness

router = APIRouter(prefix="/api/groundedness", tags=["groundedness"])


@router.post("/{turn_id}", summary="Grade a gold-set turn claim by claim")
async def grade(turn_id: str) -> Dict[str, Any]:
    # The judge client is blocking urllib, shared with the eval harness.
    result = await run_in_threadpool(groundedness.grade_turn, turn_id)
    if result is None:
        raise HTTPException(404, "No gold-set turn waiting to be graded with that id.")
    return result
