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
from app.guards import LocalOnlyMiddleware
from app.routers import chat, health, library, sessions, telemetry, tutor
from app.web import SpaFiles, resolve_web_dir
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
        # Same reasoning as startup: a cold model is a slow first answer, not a
        # broken server.
        logger.warning("Model warm-up skipped: %s", exc.detail)
    except Exception:  # noqa: BLE001 - a background task must never die silently
        logger.exception("Unexpected failure warming the model")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await client.startup()
    # Opening the library never raises: an unavailable corpus degrades the
    # tutor to model-only answers, and /health explains why.
    rag_service.open_store()
    logger.info("Ollama host: %s | default model: %s", settings.ollama_host, settings.ollama_model)
    try:
        version = await client.version()
        names = [m.get("name", "") for m in await client.list_models()]
        logger.info("Connected to Ollama %s | local models: %s", version, ", ".join(names) or "none")
        if not any(n == settings.ollama_model or n.split(":")[0] == settings.ollama_model for n in names):
            logger.warning(
                "Model '%s' is not installed. Run: ollama pull %s",
                settings.ollama_model,
                settings.ollama_model,
            )
    except OllamaError as exc:
        # Never block startup: /health reports the problem and the frontend can
        # render a 'model unavailable' state instead of failing to connect.
        logger.warning("Ollama unavailable at startup: %s %s", exc.detail, exc.hint or "")

    warm_task: Optional[asyncio.Task] = None
    if settings.warm_model_on_startup:
        warm_task = asyncio.create_task(_warm_model())

    yield

    # Stop the warm-up before closing the HTTP client it is using.
    if warm_task is not None and not warm_task.done():
        warm_task.cancel()
        with suppress(asyncio.CancelledError):
            await warm_task
    await client.shutdown()
    rag_service.close_store()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
    # A packaged device has no audience for the interactive docs, and they
    # advertise the library write routes to anyone poking at the URL bar.
    docs_url=None if settings.packaged else "/docs",
    redoc_url=None if settings.packaged else "/redoc",
    openapi_url=None if settings.packaged else "/openapi.json",
    description=(
        "Offline AI tutor backend. Every completion is produced locally by "
        "Ollama -- no external API calls, no internet required at request time."
    ),
)

# The packaged build serves the frontend from this same process, so every
# request is same-origin and CORS is not merely unnecessary but unwanted. The
# launcher sets CORS_ORIGINS empty; a developer running Vite on its own port
# keeps the permissive default.
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

if settings.packaged:
    app.add_middleware(LocalOnlyMiddleware)


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
app.include_router(tutor.router)
app.include_router(library.router)
app.include_router(telemetry.router)


@app.get("/api/index", tags=["health"], summary="API index")
async def api_index():
    return {
        "name": settings.app_name,
        "version": settings.version,
        "docs": None if settings.packaged else "/docs",
        "health": "/health",
        "model": settings.ollama_model,
        "offline": True,
    }


# Mounted last, and it must stay last: a mount at "/" matches every path, so
# any route registered after it is unreachable.
_web_dir = resolve_web_dir(settings.web_dir)
if _web_dir is not None:
    app.mount("/", SpaFiles(directory=_web_dir, html=True), name="web")
    logger.info("Serving frontend from %s", _web_dir)
