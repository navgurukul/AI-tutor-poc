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


async def _warm_stt() -> None:
    """Load the IndicConformer model at boot too, so the first Hindi/Marathi
    turn doesn't pay its ~3s load. Blocking (sherpa), so run it off the loop;
    best-effort -- warm() returns False rather than raising when files are
    missing."""
    started = time.monotonic()
    logger.info("Warming up IndicConformer STT model in the background...")
    ok = await asyncio.to_thread(stt_service.warm)
    logger.info(
        "STT warm-up %s in %.1fs.",
        "done" if ok else "skipped (model not available)",
        time.monotonic() - started,
    )


async def _warm_tts() -> None:
    """Load the Piper TTS voice at boot so the first non-English answer's first
    sentence isn't delayed by it. Blocking (sherpa), best-effort."""
    started = time.monotonic()
    logger.info("Warming up Piper TTS voice in the background...")
    ok = await asyncio.to_thread(tts_service.warm)
    logger.info(
        "TTS warm-up %s in %.1fs.",
        "done" if ok else "skipped (voice not available)",
        time.monotonic() - started,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await client.startup()
    # Opening the library never raises: an unavailable corpus degrades the
    # tutor to model-only answers, and /health explains why.
    rag_service.open_store()
    logger.info("Ollama host: %s | model: %s", settings.ollama_host, settings.ollama_model)
    warm_task: Optional[asyncio.Task] = None
    stt_warm_task = (
        asyncio.create_task(_warm_stt()) if settings.warm_model_on_startup else None
    )
    tts_warm_task = (
        asyncio.create_task(_warm_tts()) if settings.warm_model_on_startup else None
    )
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
        elif settings.warm_model_on_startup:
            warm_task = asyncio.create_task(_warm_model())
    except OllamaError as exc:
        # Never block startup: /health reports the problem and the frontend can
        # render a 'model unavailable' state instead of failing to connect.
        logger.warning("Ollama unavailable at startup: %s %s", exc.detail, exc.hint or "")

    yield

    # Stop the warm-ups before closing the HTTP client the model one is using.
    for task in (warm_task, stt_warm_task, tts_warm_task):
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
