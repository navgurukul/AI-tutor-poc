"""Offline text-to-speech: POST text, get a WAV back.

Used by the frontend for **non-English** answers only — English is spoken by the
browser's own speechSynthesis and never reaches the backend. Runs sherpa-onnx
with a Piper VITS voice (see app/services/tts.py).
"""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services import tts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tts", tags=["tts"])


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000, examples=["नमस्ते, आज हम क्या सीखेंगे?"])


@router.get("", summary="Is offline text-to-speech ready?")
async def tts_status() -> dict:
    """Also triggers the lazy voice-model load."""
    ready = await run_in_threadpool(tts.warm)
    return {"ready": ready}


@router.post("", summary="Synthesize a sentence to WAV")
async def synthesize(request: TtsRequest) -> Response:
    try:
        wav = await run_in_threadpool(tts.synthesize, request.text)
    except tts.TtsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not wav:
        raise HTTPException(status_code=422, detail="empty text")
    return Response(content=wav, media_type="audio/wav")
