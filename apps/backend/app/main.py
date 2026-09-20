"""FastAPI entrypoint for the offline AI Tutor POC.

Run with:  uvicorn app.main:app --reload --port 8000
Docs at:   http://localhost:8000/docs
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import chat, health, library, sessions, stt, tts, tutor

from app.services import stt as stt_service
from app.services import tts as tts_service
from app.services.ollama_client import OllamaError, client
from app.services.rag import service as rag_service
from app.services.rag import spell
from app.services.rag.embeddings import embed_query

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
)
logger = logging.getLogger("ai-tutor")


async def _warm_model() -> None:
    """Load the model into RAM so the first question doesn't pay for it.

    Deliberately fire-and-forget: the server starts serving immediately while
    the weights load in the background, which overlaps neatly with the frontend
    still downloading its Piper voice model.
    """
    started = time.perf_counter()
    try:
        await client.warm()
        # Timed here rather than from the response: Ollama reports
        # `load_duration: 0` on a load-only call, so wall time is the real cost.
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "Warmed '%s' in %dms (keep_alive=%s, num_ctx=%d)",
            settings.ollama_model,
            elapsed_ms,
            settings.ollama_keep_alive,
            settings.num_ctx,
        )
    except OllamaError as exc:
        # A cold model is a slow first answer, not a broken server.
        logger.warning("Model warm-up skipped: %s", exc.detail)
    except Exception:  # noqa: BLE001 - a background task must never die silently
        logger.exception("Unexpected failure warming the model")


async def _warm_cpu() -> None:
    """Run a real, sustained generation at boot -- not just a weight load --
    so the CPU is already at its throttled steady state before the student's
    first real question, instead of transitioning into it mid-session.

    `_warm_model` only loads weights (`done_reason: "load"`, zero decode); it
    proves the model is resident but never taxes the CPU. This box's own
    documented thermal variance (up to 2.4x, EXP-002) is about the chip
    heating up UNDER sustained load -- a cold first real question starts on a
    cool, fast chip and can look deceptively quick, only for a turn a few
    questions later to land on the same chip once it has heated up and
    throttled. Paying that transition here, on a throwaway prompt while the
    student is still in the lobby, trades away that misleading fast-first-turn
    for a steady-state number that holds from turn one.

    A real ~120-token decode, not num_predict=1: prefill alone does not
    sustain load long enough to matter on a CPU this size. Best-effort and
    fully discarded -- this touches no session, and a failure here costs a
    less consistent first turn, not a broken server.
    """
    if not settings.warm_cpu_on_startup:
        return
    started = time.monotonic()
    try:
        await client.chat(
            [{"role": "user", "content": "Write a short paragraph about rivers."}],
            max_tokens=120,
        )
        logger.info("CPU warm-up (sustained generation) done in %.1fs.", time.monotonic() - started)
    except OllamaError as exc:
        logger.warning("CPU warm-up skipped: %s", exc.detail)
    except Exception:  # noqa: BLE001 - a background task must never die silently
        logger.exception("Unexpected failure during CPU warm-up")


async def _warm_stt() -> None:
    """Load settings.warm_language's recognizer at boot, so the first turn in it
    doesn't pay the ~3s load. Blocking (sherpa), so run it off the loop;
    best-effort -- warm() returns False rather than raising when files are
    missing."""
    lang = settings.warm_language.strip()
    if not lang:
        logger.info("STT warm-up skipped (warm_language is empty).")
        return
    started = time.monotonic()
    logger.info("Warming up the %s STT model in the background...", lang)
    if await asyncio.to_thread(stt_service.warm, lang):
        logger.info("STT warm-up done in %.1fs.", time.monotonic() - started)
    else:
        logger.info("STT warm-up skipped (%s model not installed).", lang)


async def _warm_tts() -> None:
    """Load settings.warm_language's Piper voice at boot so the first spoken
    sentence isn't delayed by it. Blocking (sherpa), best-effort — warm()
    returns False rather than raising when the voice folder is missing."""
    lang = settings.warm_language.strip()
    if not lang:
        logger.info("TTS warm-up skipped (warm_language is empty).")
        return
    started = time.monotonic()
    logger.info("Warming up the %s Piper voice in the background...", lang)
    if await asyncio.to_thread(tts_service.warm, lang):
        logger.info("TTS warm-up done in %.1fs.", time.monotonic() - started)
    else:
        logger.info("TTS warm-up skipped (%s voice not installed).", lang)


async def _warm_embeddings() -> None:
    """Load the embedding model so the FIRST question doesn't pay for it.

    Everything else about a turn was warmed here already -- the LLM, the
    recognizer, the voice -- but not bge-m3, and it is the one model the lobby
    warm-up can never touch: that call deliberately skips retrieval, because
    the phrase "warm up" would pull noise passages and leave a prefix no real
    question matches.

    So the first real question loaded 1.2 GB from disk while the student
    waited. Measured 2026-09-14 on the first turn after a two-day-cold start:
    `retrieval 11211ms (embed 10774)` of an 18.0 s wait to the first token.

    The model stays resident afterwards (rag_embed_query_keep_alive = -1).
    Best-effort: a failure here costs a slow first question, not a broken
    server, and the store may be unavailable entirely.
    """
    if not settings.rag_enabled:
        logger.info("Embedding warm-up skipped (retrieval disabled).")
        return
    # The STORE's model, not config's: after a re-embed cutover they differ,
    # and warming the wrong one leaves the real one cold.
    model = rag_service.store.embedding_model if rag_service.store.is_open else None
    started = time.monotonic()
    logger.info("Warming up the embedding model in the background...")
    try:
        await embed_query("warm up", model=model)
        logger.info(
            "Embedding warm-up done in %.1fs (%s).",
            time.monotonic() - started,
            model or settings.rag_embedding_model,
        )
    except OllamaError as exc:
        logger.warning("Embedding warm-up skipped: %s", exc.detail)
    except Exception:  # noqa: BLE001 - a background task must never die silently
        logger.exception("Unexpected failure warming the embedding model")


async def _warm_in_order(include_model: bool) -> None:
    """Warm-ups run one after another rather than in parallel.

    Started together they load seven models at once on a four-core box, and the
    one the UI actually waits on — the LLM, which gates the mic — is the one
    that gets starved: a boot where Ollama reported `load_duration 54ms` still
    took 55s to answer its warm-up prompt, all of it contention. Speech models
    aren't needed until the user has finished speaking, so they queue behind it,
    and the embedding model queues behind those.
    """
    if include_model:
        await _warm_model()
    await _warm_stt()
    await _warm_tts()
    # The lobby's readiness check waits on the three above, while embeddings
    # and the CPU pre-heat are not needed until the student has actually asked
    # something -- both run after, so neither delays the mic going live.
    await _warm_embeddings()
    if include_model:
        await _warm_cpu()
    # Last, and in its own thread: a pure-Python scan of the corpus that must
    # not contend with anything above. Until it finishes, questions are
    # simply searched as spoken.
    spell.ensure_built(rag_service.store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await client.startup()
    # Opening the library never raises: an unavailable corpus degrades the
    # tutor to model-only answers, and /health explains why.
    rag_service.open_store()
    logger.info("Ollama host: %s | model: %s", settings.ollama_host, settings.ollama_model)
    warm_task: Optional[asyncio.Task] = None
    model_present = False
    try:
        version = await client.version()
        names = [m.get("name", "") for m in await client.list_models()]
        logger.info("Connected to Ollama %s | local models: %s", version, ", ".join(names) or "none")
        model_present = any(
            n == settings.ollama_model or n.split(":")[0] == settings.ollama_model
            for n in names
        )
        if not model_present:
            logger.warning(
                "Model '%s' is not installed. Run: ollama pull %s",
                settings.ollama_model,
                settings.ollama_model,
            )
    except OllamaError as exc:
        # Never block startup: /health reports the problem and the frontend can
        # render a 'model unavailable' state instead of failing to connect.
        logger.warning("Ollama unavailable at startup: %s %s", exc.detail, exc.hint or "")

    # One chain, not three racing tasks. Speech still warms when the model is
    # missing or Ollama is down — it doesn't depend on either.
    if settings.warm_model_on_startup:
        warm_task = asyncio.create_task(_warm_in_order(model_present))

    yield

    # Stop the warm-ups before closing the HTTP client the model one is using.
    for task in (warm_task,):
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    await client.shutdown()
    rag_service.close_store()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
    description=(
        "Offline AI tutor backend. Every completion is produced locally by "
        "Ollama -- no external API calls, no internet required at request time."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(OllamaError)
async def ollama_error_handler(request: Request, exc: OllamaError) -> JSONResponse:
    """Turn client failures into actionable JSON instead of a bare 500."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "hint": exc.hint},
    )


app.include_router(health.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(stt.router)
app.include_router(tts.router)
app.include_router(tutor.router)
app.include_router(library.router)


@app.get("/", tags=["health"], summary="API index")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/health",
        "model": settings.ollama_model,
        "offline": True,
    }
