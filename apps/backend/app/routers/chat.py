"""Conversational tutor endpoints: buffered and streaming."""

import json
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.config import settings
from app.schemas import (
    ChatRequest,
    ChatResponse,
    RetrievalMetrics,
    Source,
    TurnMetrics,
    Usage,
)
from app.services.ollama_client import OllamaError, build_usage, client
from app.services.sessions import store
from app.services.rag import service as library
from app.services.rag.metrics import elapsed_ms, format_turn, groundedness
from app.services.rag.query import estimate_tokens
from app.services.rag.retrieval import (
    build_context_block,
    citations,
    fit_to_budget,
    pinned_context,
    retrieve,
    trim_passages,
)
from app.services.rag.store import Retrieved
from app.services.tutor import (
    build_turn_message,
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


def _effective_max_tokens(requested: Optional[int], profile) -> Optional[int]:
    """Devanagari needs 2-4x the tokens English does for the same answer, so a
    non-English turn gets the bigger cap. An explicit request wins (the
    frontend's 1-token warm-up must stay 1); None lets ollama_client fall back to
    settings.max_tokens."""
    if requested is not None:
        return requested
    language = ((getattr(profile, "language", None) or "English")).strip().lower()
    if language and language != "english":
        return settings.max_tokens_non_english
    return None


def _is_pinned(profile) -> bool:
    """Is the whole corpus small enough to sit in the system prompt?

    Decides where the excerpts go. Pinned, the block is identical on every turn,
    so it belongs in the system prompt where it caches once and is never re-read.
    Retrieved per question, it changes every turn, so it belongs inside the turn
    — putting it in the system prompt would shift everything after it and fork
    the prompt (27.7 vs 5.3 ms/token, measured 2026-09-10).

    Cheap to call: pinned_context memoises per (grade, subject, medium).
    """
    return pinned_context(
        library.store,
        grade=grade_from_profile(profile),
        subject=(profile.subject if profile else None),
        language=(profile.language if profile else None),
    ) is not None


# Words that point back at the previous answer. Matched on whole words after
# stripping punctuation -- \b does not work for Devanagari, whose vowel signs are
# not word characters -- and only in a SHORT message, because a long one that
# happens to contain "this" is usually a new question.
_FOLLOWUP_WORDS = frozenset({
    # English
    "this", "that", "it", "its", "these", "those", "they", "them",
    "example", "examples", "more", "again", "elaborate", "simpler",
    # Hindi
    "इस", "इसका", "इसकी", "इसके", "इसे", "इन", "इनका", "इनकी", "इनके", "इन्हें",
    "यह", "ये", "उस", "उसका", "उसकी", "उसके", "उसे", "वह", "वो", "उदाहरण", "दोबारा",
    # Marathi
    "हे", "ते", "याचे", "याची", "याचा", "त्याचे", "त्याची", "त्याचा",
})
_FOLLOWUP_MAX_WORDS = 8
_FOLLOWUP_STRIP = "?.!,;:।॥\"'()"


def _is_followup(message: str) -> bool:
    """A short message that refers back to what was just discussed."""
    words = [w.strip(_FOLLOWUP_STRIP).lower() for w in message.split()]
    words = [w for w in words if w]
    return 0 < len(words) <= _FOLLOWUP_MAX_WORDS and any(w in _FOLLOWUP_WORDS for w in words)


async def _retrieve_context(
    message: str, profile, session=None
) -> Tuple[str, List[dict], List[Retrieved], Optional[RetrievalMetrics]]:
    """Textbook excerpts for this question.

    Returns the prompt block, the citations for the UI, the hits themselves
    (groundedness needs their text once the answer exists) and the trace of how
    retrieval got there -- or None for the trace when metrics are switched off,
    in which case retrieval fills nothing.

    Scoped to the grade, subject and medium picked in the lobby, so a Class 6
    question cannot be answered out of a Class 11 chapter, and a Hindi-medium
    session cannot be answered out of a same-grade English book that bge-m3
    (being cross-lingual) happens to rank first.

    The session's language goes with it. The ASR selection and the UI toggle
    both already know it, and it decides which relevance ceiling applies --
    getting it from the text instead is what discards a correct Hindi hit.
    """
    trace = RetrievalMetrics() if settings.metrics_enabled else None

    # Pinned corpus: the same block every turn, so the prompt prefix is stable
    # and Ollama can reuse its KV cache. Nothing is ranked, so there is no
    # embedding call and no search -- which is also why the trace carries no
    # distances. Falls through to real retrieval when the corpus is too big.
    # Scoped to what the student picked in the lobby. Pinning takes every
    # matching chunk rather than the best few, so without these filters a
    # multi-book library would land whole in the prompt.
    pinned = pinned_context(
        library.store,
        grade=grade_from_profile(profile),
        subject=(profile.subject if profile else None),
        language=(profile.language if profile else None),
    )
    if pinned is not None:
        block, hits = pinned
        if trace is not None:
            trace.returned = len(hits)
            trace.context_tokens = estimate_tokens(block)
            trace.abstained = False
        return block, citations(hits), hits, trace

    # A follow-up about the last answer keeps its passage: no embedding, no
    # search, and nothing pasted, because the passage is already in the
    # conversation a few lines up. Citations and groundedness still see it.
    if (settings.rag_followup_reuse and session is not None
            and session.last_hit_ids and _is_followup(message)):
        hits = library.store.chunks_by_ids(session.last_hit_ids)
        if hits:
            if trace is not None:
                trace.returned = len(hits)
                trace.context_tokens = 0
                trace.abstained = False
                trace.abstain_reason = "follow-up: kept the previous passage, no new search"
            return "", citations(hits), hits, trace

    hits = await retrieve(
        library.store,
        message,
        grade=grade_from_profile(profile),
        subject=(profile.subject if profile else None),
        language=(profile.language if profile else None),
        metrics=trace,
    )
    # Trim each passage to the sentences that bear on the question BEFORE the
    # budget is applied, so the budget counts what the model will actually read
    # rather than what was ranked. Citations still point at the whole chunk's
    # page, which is what a student needs to find it in the book.
    hits = trim_passages(hits, message)
    # k falls before a passage is cut.
    hits = fit_to_budget(hits, metrics=trace)

    # Paste in only the passages this session has not already seen.
    #
    # Excerpts live inside the turn now (build_turn_message), so a chunk that
    # arrived on an earlier turn is still sitting in the conversation and still
    # in Ollama's cache. Sending it again costs ~110 NEW tokens -- about 5.5s at
    # the measured ~50ms per new token -- to tell the model something it can
    # already read a few lines up.
    #
    # This is what makes a follow-up cheap without leaving a new topic
    # ungrounded: ask about the same thing and nothing is added, move to a new
    # topic and only its passage is.
    #
    # `hits` stays whole. The answer genuinely is grounded in the old passages
    # as well as the new, so citations and groundedness must still see them --
    # it is only the text pasted into THIS turn that shrinks.
    fresh = hits
    if session is not None and settings.rag_dedup_context:
        known = set(session.context_chunk_ids)
        fresh = [h for h in hits if h.chunk_id not in known]
        session.remember_chunks([h.chunk_id for h in fresh])

    if session is not None:
        session.last_hit_ids = [h.chunk_id for h in hits]

    block = build_context_block(fresh)
    if trace is not None:
        trace.context_tokens = estimate_tokens(block)
    return block, citations(hits), hits, trace


def _turn_metrics(
    trace: RetrievalMetrics,
    usage: Dict[str, Any],
    *,
    retrieval_ms: float,
    llm_ms: float,
    retry_ms: float,
    total_ms: float,
    ttft_ms: Optional[float],
    reply: str,
    hits: List[Retrieved],
) -> TurnMetrics:
    """Assemble one turn's numbers from the two clocks that measured it.

    `overhead_ms` is the wall clock the model cannot account for: HTTP to the
    Ollama daemon, JSON, and time the event loop spent elsewhere. It is
    normally small, and when it is not, the fix is not in the prompt.
    """
    model_ms = usage["load_duration_ms"] + usage["prompt_eval_ms"] + usage["eval_ms"]
    grounded, grounded_note = groundedness(reply, hits)
    return TurnMetrics(
        retrieval=trace,
        retrieval_ms=retrieval_ms,
        ttft_ms=ttft_ms,
        llm_ms=llm_ms,
        retry_ms=retry_ms,
        total_ms=total_ms,
        load_ms=usage["load_duration_ms"],
        prefill_ms=usage["prompt_eval_ms"],
        decode_ms=usage["eval_ms"],
        overhead_ms=round(max(0.0, total_ms - retrieval_ms - model_ms - retry_ms), 1),
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        tokens_per_second=usage["tokens_per_second"],
        groundedness=grounded,
        groundedness_note=grounded_note,
    )


# In-flight primes. asyncio holds only a weak reference to a task, so one that
# nothing else points at can be collected before it runs.
_PRIME_TASKS: set = set()


def _reprime_after_reply(session, model: Optional[str], pinned_block: Optional[str]) -> None:
    """Re-read the answer just given, in the background, before the next question.

    llama.cpp saves a cache checkpoint only where a prompt ends, which is just
    before the reply -- so without this, every follow-up re-reads the whole
    previous answer while the student waits (see `ollama_reprime_after_reply`).

    The prime must be EXACTLY the start of the next turn's prompt or its
    checkpoint is useless. The next turn keeps the last `max_history_messages`
    including its new question, so its history is the last limit-1 of what is
    stored now. Once the window is full that also moves the slide -- oldest
    message dropped, everything behind it re-read -- off the student's wait.

    If the student asks before it finishes, their request queues behind work it
    would otherwise have had to do itself; it is never slower than not priming.
    """
    if not settings.ollama_reprime_after_reply:
        return
    limit = settings.max_history_messages
    if limit == 1:
        return  # the next turn carries no history, so there is nothing to keep
    history = session.history(limit - 1) if limit > 1 else session.history(0)
    messages = build_chat_messages(history, session.profile, pinned_block)

    async def run() -> None:
        started = time.perf_counter()
        try:
            out = await client.prime(messages, model=model)
            logger.info(
                "re-prime %.0fms | prefill %.0fms (%s tok) -- next turn resumes after the reply",
                elapsed_ms(started),
                (out.get("prompt_eval_duration") or 0) / 1e6,
                out.get("prompt_eval_count"),
            )
        except Exception as exc:  # noqa: BLE001 - an optimisation must never fail a turn
            logger.warning("Re-prime after reply failed; the next turn will re-read it: %s", exc)

    task = asyncio.create_task(run())
    _PRIME_TASKS.add(task)
    task.add_done_callback(_PRIME_TASKS.discard)


@router.post("/chat", response_model=ChatResponse, summary="Send a message (buffered)")
async def chat(request: ChatRequest) -> ChatResponse:
    """Full reply in one response. Simple to integrate; use /chat/stream for
    token-by-token UX."""
    turn_started = time.perf_counter()
    session = await store.get_or_create(request.session_id, request.profile)
    # Added after retrieval — the excerpts belong to the turn, not the persona.
    temperature = _effective_temperature(request.temperature, session.profile)
    max_tokens = _effective_max_tokens(request.max_tokens, session.profile)
    # A throwaway one-token call from the frontend on page load, not a question
    # anyone is waiting on. It decides three things: whether to retrieve at all
    # (below), whether to skip the socratic re-ask (a one-token reply cannot end
    # with "?"), and how the turn is labelled in the log, so warm-up cost is not
    # averaged in with real turns.
    warming_up = (request.max_tokens or settings.max_tokens) <= 2

    retrieval_started = time.perf_counter()
    # A warm-up is only worth anything if it assembles the SAME prefix a real
    # question will, because that is what Ollama's KV cache reuses.
    #
    # Which prefix that is depends on the mode. With the corpus pinned, the
    # excerpts are part of every prompt and are identical every turn, so the
    # warm-up must include them -- and doing so is free, since pinning does no
    # embedding and no search. With per-question retrieval it must NOT: the
    # warm-up's message is the literal string "warm up", so its passages are
    # noise, and worse than noise. Measured 2026-09-09, that warm-up pulled 587
    # tokens of unrelated textbook, prefilled 867 tokens, cost 50 SECONDS, and
    # left a prefix no real question could match, because the excerpts change
    # with every question.
    warm_can_pin = warming_up and pinned_context(
        library.store,
        grade=grade_from_profile(session.profile),
        subject=(session.profile.subject if session.profile else None),
        language=(session.profile.language if session.profile else None),
    ) is not None
    if warming_up and not warm_can_pin:
        # An empty trace rather than None: metrics_enabled is what decides
        # whether a trace exists, and _turn_metrics requires one when it is on.
        context, sources, hits = None, [], []
        trace = RetrievalMetrics() if settings.metrics_enabled else None
    else:
        context, sources, hits, trace = await _retrieve_context(
            request.message, session.profile, session
        )
    retrieval_ms = elapsed_ms(retrieval_started)
    pinned = _is_pinned(session.profile)
    session.add(
        "user",
        build_turn_message(request.message, session.profile, None if pinned else context),
    )
    messages = build_chat_messages(
        session.history(settings.max_history_messages),
        session.profile,
        context if pinned else None,
    )
    retry_ms = 0.0
    try:
        llm_started = time.perf_counter()
        response = await client.chat(
            messages,
            model=request.model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        llm_ms = elapsed_ms(llm_started)

        reply = (response.get("message") or {}).get("content", "").strip()

        # Socratic mode drifts into lecturing on this model; re-ask once when it
        # does. Skip it for a warm-up call (max_tokens 1) -- the 1-token reply
        # can't end with "?" but there's nothing to re-ask.
        if not warming_up and needs_socratic_retry(reply, session.profile):
            logger.info("Socratic reply drifted into an explanation; re-asking once.")
            retry_started = time.perf_counter()
            retry = await client.chat(
                socratic_retry_messages(messages, reply, request.message),
                model=request.model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # Timed even when the retry is discarded below: the student waited
            # for it either way, and a rejected retry is the worse case, not a
            # free one.
            retry_ms = elapsed_ms(retry_started)
            retry_reply = (retry.get("message") or {}).get("content", "").strip()
            if retry_reply.endswith("?"):
                reply, response = retry_reply, retry
    except Exception:
        # Drop the student's turn so a retry does not stack two user messages.
        session.pop_last()
        raise

    session.add("assistant", reply)
    if not warming_up:
        _reprime_after_reply(session, request.model, context if pinned else None)

    usage = build_usage(response)
    metrics = None
    if trace is not None:
        metrics = _turn_metrics(
            trace,
            usage,
            retrieval_ms=retrieval_ms,
            llm_ms=llm_ms,
            retry_ms=retry_ms,
            total_ms=elapsed_ms(turn_started),
            # A buffered turn has no first token to time: nothing leaves the
            # server until the whole answer exists. Reporting llm_ms here
            # instead would read as a TTFT this endpoint cannot deliver.
            ttft_ms=None,
            reply=reply,
            hits=hits,
        )
        logger.info("%s", format_turn(metrics, "warm-up" if warming_up else "turn"))

    return ChatResponse(
        session_id=session.session_id,
        reply=reply,
        model=response.get("model", request.model or settings.ollama_model),
        usage=Usage(**usage),
        created_at=datetime.now(timezone.utc),
        sources=[Source(**s) for s in sources],
        metrics=metrics,
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
    turn_started = time.perf_counter()
    session = await store.get_or_create(session_id, profile)
    # The user turn is added AFTER retrieval, because the excerpts are part of
    # it — see build_turn_message. Storing the augmented text is what makes the
    # replay on later turns byte-identical to what was sent, which is the whole
    # basis of the cache holding.
    temperature = _effective_temperature(temperature, session.profile)
    max_tokens = _effective_max_tokens(max_tokens, session.profile)
    yield _sse(
        {
            "type": "start",
            "session_id": session.session_id,
            "model": model or settings.ollama_model,
        }
    )

    chunks = []
    try:
        retrieval_started = time.perf_counter()
        context, sources, hits, trace = await _retrieve_context(
            message, session.profile, session
        )
        retrieval_ms = elapsed_ms(retrieval_started)
        if sources:
            # Emitted before the first token so the UI can show what the answer
            # is grounded in while it is still being written.
            yield _sse({"type": "sources", "sources": sources})
        pinned = _is_pinned(session.profile)
        session.add(
            "user",
            build_turn_message(message, session.profile, None if pinned else context),
        )
        messages = build_chat_messages(
            session.history(settings.max_history_messages),
            session.profile,
            context if pinned else None,
        )
        llm_started = time.perf_counter()
        ttft_ms: Optional[float] = None
        async for chunk in client.chat_stream(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        ):
            token = (chunk.get("message") or {}).get("content", "")
            if token:
                if ttft_ms is None:
                    # Measured from the top of the turn, not from llm_started:
                    # retrieval is part of what the student waited through, and
                    # a TTFT that excludes it would go on looking healthy as
                    # retrieval got slower.
                    ttft_ms = elapsed_ms(turn_started)
                chunks.append(token)
                yield _sse({"type": "token", "content": token})
            if chunk.get("done"):
                reply = "".join(chunks).strip()
                session.add("assistant", reply)
                _reprime_after_reply(session, model, context if pinned else None)
                usage = build_usage(chunk)
                done: Dict[str, Any] = {
                    "type": "done",
                    "session_id": session.session_id,
                    "reply": reply,
                    "usage": usage,
                }
                if trace is not None:
                    metrics = _turn_metrics(
                        trace,
                        usage,
                        retrieval_ms=retrieval_ms,
                        llm_ms=elapsed_ms(llm_started),
                        retry_ms=0.0,
                        total_ms=elapsed_ms(turn_started),
                        ttft_ms=ttft_ms,
                        reply=reply,
                        hits=hits,
                    )
                    logger.info("%s", format_turn(metrics))
                    # Sent with `done` rather than as its own frame: these are
                    # read after the answer, and the retrieval half of them
                    # matters most when `sources` never fired at all.
                    done["metrics"] = metrics.model_dump()
                yield _sse(done)
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
