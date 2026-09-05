"""Offline text-to-speech: POST a sentence + language, get a WAV back.

One Piper voice per language (see app/services/tts.py), run through sherpa-onnx
on the backend — the same engine and the same request shape as /api/stt, so the
two halves of the speech pipeline stay symmetrical.
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services import tts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tts", tags=["tts"])

_DEFAULT_LANG = "English"


class TtsRequest(BaseModel):
    text: str = Field(
        ..., min_length=1, max_length=2000, examples=["नमस्ते, आज हम क्या सीखेंगे?"]
    )


@router.get("", summary="Which offline TTS languages are ready?")
async def tts_status(language: str | None = Query(None)) -> dict:
    """With `?language=`, reports (and lazily loads) that one; otherwise lists
    every language whose voice is installed."""
    if language:
        ready = await run_in_threadpool(tts.is_ready, language)
        return {"ready": ready, "language": language}
    langs = await run_in_threadpool(tts.available_languages)
    return {"ready": len(langs) > 0, "languages": langs}


@router.post("", summary="Synthesize a sentence to WAV")
async def synthesize(
    request: TtsRequest, language: str = Query(_DEFAULT_LANG)
) -> Response:
    try:
        wav = await run_in_threadpool(tts.synthesize, request.text, language)
    except tts.TtsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not wav:
        raise HTTPException(status_code=422, detail="empty text")
    return Response(content=wav, media_type="audio/wav")
