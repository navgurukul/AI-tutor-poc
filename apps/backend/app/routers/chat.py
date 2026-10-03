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
from app.services import groundedness, turndetail, turnlog
from app.services.sessions import store
from app.services.rag import hybrid
from app.services.tutor import (
    build_tutor_messages,
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


async def _retrieve_context(message: str) -> tuple:
    """Textbook excerpts for this question, as (prompt block, citations, detail).

    AFE-Learning-App's retrieval (rag.hybrid) since stage 3 of the golden
    comparison: the question exactly as typed, no grade or subject scoping, no
    follow-up carry and no passage shortening. `detail` is the turn-log view of
    the passages that went into the prompt.
    """
    chunks = await hybrid.query(message)
    cited = [
        {
            "title": hybrid.source_name(c),
            "heading": hybrid.breadcrumb(c),
            # AFE's chunks carry no page numbers; 0 means "unknown".
            "page_start": 0,
            "page_end": 0,
            "grade": None,
            "subject": None,
            "distance": round(c.distance, 4) if c.distance is not None else 0.0,
            "excerpt": c.text,
        }
        for c in chunks
    ]
    return hybrid.build_context_block(chunks), cited, turndetail.hybrid_chunks(chunks)


def _new_turn_id() -> str:
    """Short id shared by the backend and frontend rows for one turn."""
    return uuid.uuid4().hex[:12]


@router.post("/chat", response_model=ChatResponse, summary="Send a message (buffered)")
async def chat(request: ChatRequest) -> ChatResponse:
    """Full reply in one response. Simple to integrate; use /chat/stream for
    token-by-token UX."""
    session = await store.get_or_create(request.session_id, request.profile)
    session.add("user", request.message)

    context, sources, _ = await _retrieve_context(request.message)
    messages = build_tutor_messages(request.message, session.previous_question(), context)
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
    context_max_chars: Optional[int] = None,
    return_context: bool = False,
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
    first_token_at = 0.0
    context = ""
    sources = []
    retrieval_ms = 0
    retrieved = []
    previous_question = session.previous_question()
    try:
        retrieval_started = time.perf_counter()
        context, sources, retrieved = await _retrieve_context(message)
        retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)
        if sources:
            # Emitted before the first token so the UI can show what the answer
            # is grounded in while it is still being written.
            frame: Dict[str, Any] = {"type": "sources", "sources": sources}
            if return_context:
                # What the model actually read, after the budget. Not the same
                # as `sources`, which lists every retrieved passage including
                # any the budget cut -- so an answer can only be graded fairly
                # against this.
                frame["context"] = context
            yield _sse(frame)
        messages = build_tutor_messages(message, previous_question, context)
        # Earlier questions carried into the prompt: 1 from the second question
        # of a session on (the user turn names the previous one), else 0.
        history_sent = int(bool(previous_question))
        prompt_sent_at = time.perf_counter()
        async for chunk in client.chat_stream(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        ):
            token = (chunk.get("message") or {}).get("content", "")
            if token:
                if not chunks:
                    first_token_at = time.perf_counter()
                    ttft_ms = int((first_token_at - turn_start) * 1000)
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
                turndetail.record(
                    {
                        "ts_utc": turnlog.now_utc(),
                        "turn_id": turn_id,
                        "session_id": session.session_id,
                        "question": message,
                        "previous_question": previous_question,
                        "followup": history_sent > 0,
                        "retrieval": {
                            "ms": retrieval_ms,
                            "query": message,
                            "mode": "hybrid",
                            "budget": "{} tokens".format(settings.hybrid_max_context_tokens),
                            "top_k": settings.hybrid_top_k,
                            "context_chars": len(context),
                            "chunks": retrieved,
                        },
                        "prompt": {
                            "model": model or settings.ollama_model,
                            "options": client.options(temperature, max_tokens),
                            "messages": messages,
                            "prompt_chars": sum(len(m["content"]) for m in messages),
                        },
                        "llm": {
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                            "prefill_ms": usage.get("prompt_eval_ms", 0),
                            "decode_ms": usage.get("eval_ms", 0),
                            "load_ms": usage.get("load_duration_ms", 0),
                            "tokens_per_second": usage.get("tokens_per_second", 0),
                            # From the start of the turn (includes retrieval),
                            # and from the moment the request left for Ollama.
                            "ttft_ms": ttft_ms,
                            "ttft_after_retrieval_ms": max(
                                0, int((first_token_at - prompt_sent_at) * 1000)
                            )
                            if first_token_at
                            else 0,
                            "total_ms": int((time.perf_counter() - turn_start) * 1000),
                        },
                        "answer": reply,
                        "answer_chars": len(reply),
                    }
                )
                # A gold-set question is graded, but not here: the judge takes
                # seconds a claim, and the stream ending is what frees the UI.
                # The frontend asks for the score once it sees this flag.
                item = groundedness.match_item(message, previous_question)
                if item:
                    groundedness.remember_turn(turn_id, item, reply, context)
                yield _sse(
                    {
                        "type": "done",
                        "session_id": session.session_id,
                        "reply": reply,
                        "usage": usage,
                        "turn_id": turn_id,
                        "groundedness_pending": bool(item),
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
            context_max_chars=request.context_max_chars,
            return_context=request.return_context,
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
