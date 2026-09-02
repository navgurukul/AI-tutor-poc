"""FastAPI entrypoint for the offline AI Tutor POC.

Run with:  uvicorn app.main:app --reload --port 8000
Docs at:   http://localhost:8000/docs
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import chat, health, sessions, stt, tutor

from app.services import stt as stt_service
from app.services.ollama_client import OllamaError, client

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
)
logger = logging.getLogger("ai-tutor")


async def _warm_model() -> None:
    """Load the model into RAM at server boot so the first student's first
    question doesn't pay the ~8-20s cold start. Runs as a background task so it
    never delays startup; keep_alive=-1 then keeps it resident."""
    started = time.monotonic()
    logger.info("Warming up model '%s' in the background...", settings.ollama_model)
    load_ms = await client.warm()
    logger.info(
        "Model warm-up done in %.1fs (ollama load_duration %.0fms). Model is resident.",
        time.monotonic() - started,
        load_ms,
    )


async def _warm_stt() -> None:
    """Load every installed STT engine at boot (Moonshine for English,
    IndicConformer for Hindi/Marathi) so the first turn in any language doesn't
    pay the model load. Blocking (sherpa), run off the loop; best-effort."""
    started = time.monotonic()
    langs = await asyncio.to_thread(stt_service.available_languages)
    if not langs:
        logger.info("STT warm-up skipped (no models installed).")
        return
    logger.info("Warming up STT models %s in the background...", langs)
    for lang in langs:
        await asyncio.to_thread(stt_service.warm, lang)
    logger.info("STT warm-up done in %.1fs.", time.monotonic() - started)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await client.startup()
    logger.info("Ollama host: %s | model: %s", settings.ollama_host, settings.ollama_model)
    warm_task = None
    stt_warm_task = (
        asyncio.create_task(_warm_stt()) if settings.warm_model_on_startup else None
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
    for task in (warm_task, stt_warm_task):
        if task is not None and not task.done():
            task.cancel()
    await client.shutdown()


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
app.include_router(tutor.router)


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
