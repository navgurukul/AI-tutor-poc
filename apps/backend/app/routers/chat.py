"""Conversational tutor endpoints: buffered and streaming."""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.config import settings
from app.schemas import ChatRequest, ChatResponse, Source, Usage
from app.services.ollama_client import OllamaError, build_usage, client
from app.services import turnlog
from app.services.sessions import store
from app.services.rag import service as library
from app.services.rag.retrieval import build_context_block, citations, retrieve
from app.services.tutor import (
    build_chat_messages,
    grade_from_profile,
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


async def _retrieve_context(message: str, profile) -> tuple:
    """Textbook excerpts for this question, as (prompt block, citations).

    Scoped to the session's grade and subject so a Class 6 question cannot be
    answered out of a Class 11 chapter.
    """
    hits = await retrieve(
        library.store,
        message,
        grade=grade_from_profile(profile),
        subject=(profile.subject if profile else None),
    )
    return build_context_block(hits), citations(hits)


def _new_turn_id() -> str:
    """Short id shared by the backend and frontend rows for one turn."""
    return uuid.uuid4().hex[:12]


@router.post("/chat", response_model=ChatResponse, summary="Send a message (buffered)")
async def chat(request: ChatRequest) -> ChatResponse:
    """Full reply in one response. Simple to integrate; use /chat/stream for
    token-by-token UX."""
    session = await store.get_or_create(request.session_id, request.profile)
    session.add("user", request.message)

    context, sources = await _retrieve_context(request.message, session.profile)
    messages = build_chat_messages(
        session.history(settings.max_history_messages), session.profile, context
    )
    try:
        response = await client.chat(
            messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        reply = (response.get("message") or {}).get("content", "").strip()

        # Socratic mode drifts into lecturing on this model; re-ask once when it does.
        if needs_socratic_retry(reply, session.profile):
            logger.info("Socratic reply drifted into an explanation; re-asking once.")
            retry = await client.chat(
                socratic_retry_messages(messages, reply, request.message),
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            retry_reply = (retry.get("message") or {}).get("content", "").strip()
            # Accepted only if it is actually shorter. Was a question-mark test,
            # which the style rule no longer asks for; keeping the original on a
            # retry that rambled just as long is the point of checking at all.
            if retry_reply and len(retry_reply) < len(reply):
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
        sources=[Source(**s) for s in sources],
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
    turn_id = _new_turn_id()
    turn_start = time.perf_counter()
    yield _sse(
        {
            "type": "start",
            "session_id": session.session_id,
            "model": model or settings.ollama_model,
            # Echoed back by the frontend so its row joins this one.
            "turn_id": turn_id,
        }
    )

    chunks = []
    ttft_ms = 0
    context = ""
    sources = []
    retrieval_ms = 0
    try:
        retrieval_started = time.perf_counter()
        context, sources = await _retrieve_context(message, session.profile)
        retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)
        if sources:
            # Emitted before the first token so the UI can show what the answer
            # is grounded in while it is still being written.
            yield _sse({"type": "sources", "sources": sources})
        messages = build_chat_messages(
            session.history(settings.max_history_messages), session.profile, context
        )
        # Counted here, not at the end: by the time the row is written the reply
        # has been appended to the session, so reading the window back then
        # reports a message that was never in this prompt. Minus the system one.
        history_sent = len(messages) - 1
        async for chunk in client.chat_stream(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        ):
            token = (chunk.get("message") or {}).get("content", "")
            if token:
                if not chunks:
                    ttft_ms = int((time.perf_counter() - turn_start) * 1000)
                chunks.append(token)
                yield _sse({"type": "token", "content": token})
            if chunk.get("done"):
                reply = "".join(chunks).strip()
                session.add("assistant", reply)
                usage = build_usage(chunk)
                turnlog.log_backend_turn(
                    {
                        "ts_utc": turnlog.now_utc(),
                        "turn_id": turn_id,
                        "session_id": session.session_id,
                        "question_chars": len(message),
                        "history_msgs": history_sent,
                        "retrieval_ms": retrieval_ms,
                        "sources": len(sources),
                        "context_chars": len(context),
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "prefill_ms": usage.get("prompt_eval_ms", 0),
                        "ttft_ms": ttft_ms,
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "generation_ms": usage.get("eval_ms", 0),
                        "tokens_per_second": usage.get("tokens_per_second", 0),
                        "load_ms": usage.get("load_duration_ms", 0),
                        "total_ms": int((time.perf_counter() - turn_start) * 1000),
                        "answer_chars": len(reply),
                    }
                )
                yield _sse(
                    {
                        "type": "done",
                        "session_id": session.session_id,
                        "reply": reply,
                        "usage": usage,
                        "turn_id": turn_id,
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
