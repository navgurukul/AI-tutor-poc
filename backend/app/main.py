"""FastAPI entrypoint for the offline AI Tutor POC.

Run with:  uvicorn app.main:app --reload --port 8000
Docs at:   http://localhost:8000/docs
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import chat, health, sessions, tutor
from app.services.ollama_client import OllamaError, client

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
)
logger = logging.getLogger("ai-tutor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await client.startup()
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
    yield
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
