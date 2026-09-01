"""Offline speech-to-text endpoint for the Indian languages (IndicConformer).

The browser records a short clip and POSTs it here as a 16 kHz mono 16-bit WAV
for Hindi / Gujarati / Kannada / Marathi; sherpa-onnx + AI4Bharat's
IndicConformer turn it into text in the correct native script, fully offline.
English speech input never reaches this route.
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.services import stt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stt", tags=["stt"])

# A tutor question is short; anything much bigger is a stuck mic or a bad client.
_MAX_BYTES = 8 * 1024 * 1024


@router.get("", summary="Is offline speech-to-text ready?")
async def stt_status() -> dict:
    """Also triggers the lazy model load, so the frontend can call this when a
    non-English language is picked and show a 'preparing' state."""
    ready = await run_in_threadpool(stt.warm)
    return {"ready": ready}


@router.post("", summary="Transcribe a short WAV clip")
async def transcribe(request: Request) -> dict:
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")
    if len(raw) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="audio clip too large")

    try:
        text = await run_in_threadpool(stt.transcribe, raw)
    except stt.SttUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"text": text}
