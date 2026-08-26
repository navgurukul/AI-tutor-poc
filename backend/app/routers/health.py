"""Liveness and capability endpoints.

The frontend calls /health on boot to show an 'offline model ready' indicator
and to fail loudly (with a fix hint) when Ollama or the model is missing.
"""

from fastapi import APIRouter

from app.config import settings
from app.schemas import (
    HealthResponse,
    ModelInfo,
    ModelListResponse,
    ModelStatus,
    OllamaStatus,
)
from app.services.ollama_client import OllamaError, client
from app.services.sessions import store

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Backend + model status")
async def health() -> HealthResponse:
    """Never fails with 5xx -- it reports degradation in the body instead, so the
    frontend can always render a status panel."""
    ollama_status = OllamaStatus(reachable=False, host=settings.ollama_host)
    model_status = ModelStatus(name=settings.ollama_model, available=False)

    try:
        ollama_status.version = await client.version()
        ollama_status.reachable = True
        names = [m.get("name", "") for m in await client.list_models()]
        model_status.available_models = names
        # `ollama list` shows "qwen2.5:1.5b"; accept a bare name without a tag too.
        model_status.available = any(
            n == settings.ollama_model or n.split(":")[0] == settings.ollama_model
            for n in names
        )
    except OllamaError as exc:
        ollama_status.error = "{} {}".format(exc.detail, exc.hint or "").strip()

    healthy = ollama_status.reachable and model_status.available
    return HealthResponse(
        status="ok" if healthy else "degraded",
        app=settings.app_name,
        version=settings.version,
        ollama=ollama_status,
        model=model_status,
        active_sessions=await store.count(),
    )


@router.get(
    "/api/models", response_model=ModelListResponse, summary="Locally installed models"
)
async def list_models() -> ModelListResponse:
    raw = await client.list_models()
    models = []
    for entry in raw:
        details = entry.get("details") or {}
        models.append(
            ModelInfo(
                name=entry.get("name", ""),
                size_bytes=entry.get("size"),
                parameter_size=details.get("parameter_size"),
                quantization=details.get("quantization_level"),
                family=details.get("family"),
                modified_at=entry.get("modified_at"),
            )
        )
    return ModelListResponse(default_model=settings.ollama_model, models=models)
