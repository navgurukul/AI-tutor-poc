"""Offline text-to-speech: POST a sentence + language, get a WAV back.

One Piper voice per language (see app/services/tts.py), run through sherpa-onnx
on the backend — the same engine and the same request shape as /api/stt, so the
two halves of the speech pipeline stay symmetrical.
"""

import logging
import time

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
    """With `?language=`, loads that voice AND speaks one throwaway sentence;
    otherwise lists every language whose voice is installed.

    The lobby calls this for the chosen language while the student is still
    picking a class. Loading alone was not enough: onnxruntime pays its
    first-inference cost on the first generate(), so the student's first spoken
    sentence was the one that paid it. warm() does it once per loaded voice."""
    if language:
        ready = await run_in_threadpool(tts.warm, language)
        return {"ready": ready, "language": language}
    langs = await run_in_threadpool(tts.available_languages)
    return {"ready": len(langs) > 0, "languages": langs}


@router.post("", summary="Synthesize a sentence to WAV")
async def synthesize(
    request: TtsRequest, language: str = Query(_DEFAULT_LANG)
) -> Response:
    # Timestamped (not just a duration) so a slow /api/chat turn's prefill
    # window -- logged separately with its own timestamp -- can be directly
    # checked against whether synthesis was running at the same wall-clock
    # moment. Added 2026-09-15 chasing an isolated 2x prefill slowdown with no
    # matching increase in token count: sherpa-onnx synthesis runs in this
    # process's own threadpool, on the same 2 physical cores as Ollama's
    # separate process, so genuine OS-level contention between the two is
    # possible even though Ollama itself serializes its own requests through
    # one slot (confirmed via its own server.log) and therefore can't be the
    # thing directly slowing down its own in-progress work.
    started = time.perf_counter()
    try:
        wav = await run_in_threadpool(tts.synthesize, request.text, language)
    except tts.TtsUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not wav:
        raise HTTPException(status_code=422, detail="empty text")
    logger.info(
        "tts synth: %.0fms for %d chars (%r...)",
        (time.perf_counter() - started) * 1000,
        len(request.text),
        request.text[:30],
    )
    return Response(content=wav, media_type="audio/wav")
