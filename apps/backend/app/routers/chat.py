"""Conversational tutor endpoints: buffered and streaming."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.config import settings
from app.schemas import ChatRequest, ChatResponse, Usage
from app.services.ollama_client import OllamaError, build_usage, client
from app.services.sessions import store
from app.services.tutor import (
    build_chat_messages,
    needs_socratic_retry,
    socratic_retry_messages,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Stops nginx (if it ever sits in front) from buffering the stream.
    "X-Accel-Buffering": "no",
}


def _sse(payload: Dict[str, Any]) -> str:
    return "data: {}\n\n".format(json.dumps(payload, ensure_ascii=False))


def _effective_temperature(requested: Optional[float], profile) -> Optional[float]:
    """Small models hold the target language and script better at a lower
    temperature, so a non-English turn defaults lower. An explicit request wins;
    None lets ollama_client fall back to settings.temperature."""
    if requested is not None:
        return requested
    language = ((getattr(profile, "language", None) or "English")).strip().lower()
    if language and language != "english":
        return settings.temperature_non_english
    return None


@router.post("/chat", response_model=ChatResponse, summary="Send a message (buffered)")
async def chat(request: ChatRequest) -> ChatResponse:
    """Full reply in one response. Simple to integrate; use /chat/stream for
    token-by-token UX."""
    session = await store.get_or_create(request.session_id, request.profile)
    session.add("user", request.message)

    temperature = _effective_temperature(request.temperature, session.profile)
    messages = build_chat_messages(
        session.history(settings.max_history_messages), session.profile
    )
    try:
        response = await client.chat(
            messages,
            model=request.model,
            temperature=temperature,
            max_tokens=request.max_tokens,
        )

        reply = (response.get("message") or {}).get("content", "").strip()

        # Socratic mode drifts into lecturing on this model; re-ask once when it
        # does. Skip it for a warm-up call (max_tokens 1) -- the 1-token reply
        # can't end with "?" but there's nothing to re-ask.
        warming_up = (request.max_tokens or settings.max_tokens) <= 2
        if not warming_up and needs_socratic_retry(reply, session.profile):
            logger.info("Socratic reply drifted into an explanation; re-asking once.")
            retry = await client.chat(
                socratic_retry_messages(messages, reply, request.message),
                model=request.model,
                temperature=temperature,
                max_tokens=request.max_tokens,
            )
            retry_reply = (retry.get("message") or {}).get("content", "").strip()
            if retry_reply.endswith("?"):
                reply, response = retry_reply, retry
    except Exception:
        # Drop the student's turn so a retry does not stack two user messages.
        session.pop_last()
        raise

    session.add("assistant", reply)

    return ChatResponse(
        session_id=session.session_id,
        reply=reply,
        model=response.get("model", request.model or settings.ollama_model),
        usage=Usage(**build_usage(response)),
        created_at=datetime.now(timezone.utc),
    )


async def _stream_events(
    message: str,
    session_id: Optional[str],
    model: Optional[str],
    temperature: Optional[float],
    max_tokens: Optional[int],
    profile=None,
) -> AsyncIterator[str]:
    """Server-Sent Events: one `start`, many `token`, then `done` (or `error`).

    Errors are emitted as events rather than raised, because the HTTP status is
    already committed once streaming begins.
    """
    session = await store.get_or_create(session_id, profile)
    session.add("user", message)
    temperature = _effective_temperature(temperature, session.profile)
    yield _sse(
        {
            "type": "start",
            "session_id": session.session_id,
            "model": model or settings.ollama_model,
        }
    )

    chunks = []
    try:
        messages = build_chat_messages(
            session.history(settings.max_history_messages), session.profile
        )
        async for chunk in client.chat_stream(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        ):
            token = (chunk.get("message") or {}).get("content", "")
            if token:
                chunks.append(token)
                yield _sse({"type": "token", "content": token})
            if chunk.get("done"):
                reply = "".join(chunks).strip()
                session.add("assistant", reply)
                yield _sse(
                    {
                        "type": "done",
                        "session_id": session.session_id,
                        "reply": reply,
                        "usage": build_usage(chunk),
                    }
                )
    except OllamaError as exc:
        logger.warning("Stream failed: %s", exc.detail)
        session.pop_last()
        yield _sse({"type": "error", "detail": exc.detail, "hint": exc.hint})
    except Exception as exc:  # noqa: BLE001 - never leave the stream hanging
        logger.exception("Unexpected stream failure")
        session.pop_last()
        yield _sse({"type": "error", "detail": str(exc)})
    finally:
        yield "data: [DONE]\n\n"


@router.post("/chat/stream", summary="Send a message (SSE token stream)")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Token stream over SSE. Read it with fetch + ReadableStream."""
    return StreamingResponse(
        _stream_events(
            request.message,
            request.session_id,
            request.model,
            request.temperature,
            request.max_tokens,
            request.profile,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/chat/stream", summary="SSE token stream (EventSource-friendly)")
async def chat_stream_get(
    message: str = Query(..., min_length=1),
    session_id: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    temperature: Optional[float] = Query(None, ge=0.0, le=2.0),
    max_tokens: Optional[int] = Query(None, ge=1, le=4096),
) -> StreamingResponse:
    """Same stream as the POST variant, for the browser's native `EventSource`,
    which can only issue GET requests."""
    return StreamingResponse(
        _stream_events(message, session_id, model, temperature, max_tokens),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
