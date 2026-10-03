"""Offline speech-to-text: POST a short WAV clip + language, get text back.

One engine per language (see app/services/stt.py): IndicConformer for
Hindi/Marathi, Moonshine for English. The browser records a 16 kHz mono 16-bit
clip and POSTs it here; everything runs locally.
"""

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.services import stt
from app.services import turnlog

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
    # From the frontend when it has one (see useIndicSpeechToText.ts), so this
    # call's stt.jsonl line and its later /client-timing line can be joined by
    # the same id. Generated here instead when absent (an older frontend, a
    # direct curl/test) so every row still gets one rather than `None`.
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    request_started = time.perf_counter()
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")
    if len(raw) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="audio clip too large")

    try:
        text = await run_in_threadpool(
            stt.transcribe,
            raw,
            language,
            request_id=request_id,
            request_started=request_started,
        )
    except stt.SttUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # stt.transcribe() already wrote the one server-side log line for this
    # call (decode_ms, request_ms, audio shape, text) -- nothing left to log
    # here. request_id rides back on the response so the frontend can tag its
    # own /client-timing call with it.
    return {"text": text, "request_id": request_id}


class ClientTiming(BaseModel):
    """What the frontend alone can see: the span from 'mic stopped, start
    sending' to 'text is on screen' -- upload, decode, download and the React
    state update all in one number, on top of what the server-side log above
    already measured for its own half."""

    request_id: str
    client_total_ms: float
    clip_seconds: float | None = None
    chars: int | None = None
    # Whether the buffered clip was longer than the frontend's cap (currently
    # 30s -- see FINAL_MAX_SEC in useIndicSpeechToText.ts) and had its start
    # silently dropped before it was ever sent here.
    truncated: bool | None = None
    dropped_seconds: float | None = None


@router.post(
    "/client-timing",
    status_code=204,
    summary="Frontend-measured mic-stop-to-text-shown latency for one STT call",
)
async def client_timing(payload: ClientTiming) -> Response:
    """Fire-and-forget from the frontend, after it already has the text on
    screen -- never blocks or delays anything the student sees. Logged under
    the same "stt" event (so it lands in stt.jsonl beside the server-side
    line for the same request_id), tagged `phase="client_total"` so the two
    are easy to tell apart with `jq`."""
    turnlog.log_event(
        "stt",
        phase="client_total",
        **payload.model_dump(exclude_none=True),
    )
    return Response(status_code=204)
