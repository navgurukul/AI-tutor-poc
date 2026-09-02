"""Offline speech-to-text: POST a short WAV clip + language, get text back.

One engine per language (see app/services/stt.py): IndicConformer for
Hindi/Marathi, Moonshine for English. The browser records a 16 kHz mono 16-bit
clip and POSTs it here; everything runs locally.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.services import stt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stt", tags=["stt"])

# A tutor question is short; anything much bigger is a stuck mic or a bad client.
_MAX_BYTES = 8 * 1024 * 1024
_DEFAULT_LANG = "English"


@router.get("", summary="Which offline STT languages are ready?")
async def stt_status(language: str | None = Query(None)) -> dict:
    """With `?language=`, reports (and lazily loads) that one; otherwise lists
    every language whose model is installed."""
    if language:
        ready = await run_in_threadpool(stt.is_ready, language)
        return {"ready": ready, "language": language}
    langs = await run_in_threadpool(stt.available_languages)
    return {"ready": len(langs) > 0, "languages": langs}


@router.post("", summary="Transcribe a short WAV clip")
async def transcribe(request: Request, language: str = Query(_DEFAULT_LANG)) -> dict:
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")
    if len(raw) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="audio clip too large")

    try:
        text = await run_in_threadpool(stt.transcribe, raw, language)
    except stt.SttUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"text": text}
