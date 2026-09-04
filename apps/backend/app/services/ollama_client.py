"""Thin async wrapper over the local Ollama HTTP API.

Only three endpoints are used: /api/version, /api/tags and /api/chat. Nothing
here reaches the internet -- every call goes to the Ollama daemon on localhost.
"""

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _keep_alive() -> Any:
    """Ollama's `keep_alive` wants an int (seconds; -1 = never unload) OR a
    duration string *with a unit* ("30m"). The bare string "-1" is rejected
    ("missing unit in duration"), so coerce a plain number to int."""
    raw = str(settings.ollama_keep_alive).strip()
    try:
        return int(raw)
    except ValueError:
        return raw


class OllamaError(Exception):
    """Raised for any failure talking to Ollama, carrying an HTTP status to surface."""

    def __init__(self, detail: str, status_code: int = 502, hint: Optional[str] = None):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.hint = hint


def _keep_alive() -> Any:
    """Ollama takes `keep_alive` as either seconds (a number) or a duration
    string. Settings arrive as strings via env vars, so send whichever form the
    configured value actually is -- "-1" must go as the number -1, not the text.
    """
    raw = str(settings.ollama_keep_alive).strip()
    try:
        return int(raw)
    except ValueError:
        return raw


class OllamaClient:
    def __init__(
        self,
        host: Optional[str] = None,
        timeout: Optional[float] = None,
        connect_timeout: Optional[float] = None,
    ):
        self.host = (host or settings.ollama_host).rstrip("/")
        self._timeout = httpx.Timeout(
            timeout or settings.ollama_timeout_seconds,
            connect=connect_timeout or settings.ollama_connect_timeout_seconds,
        )
        self._client: Optional[httpx.AsyncClient] = None

    # -- lifecycle ---------------------------------------------------------
    async def startup(self) -> None:
        self._client = httpx.AsyncClient(base_url=self.host, timeout=self._timeout)

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise OllamaError("HTTP client is not initialised", status_code=500)
        return self._client

    # -- error translation -------------------------------------------------
    def _unreachable(self, exc: Exception) -> OllamaError:
        return OllamaError(
            "Cannot reach the Ollama daemon at {}.".format(self.host),
            status_code=503,
            hint="Start it with `ollama serve`, then confirm with `curl {}/api/tags`.".format(
                self.host
            ),
        )

    def _raise_for_response(self, response: httpx.Response, model: str) -> None:
        if response.status_code < 400:
            return
        body = response.text.strip()
        if response.status_code == 404:
            raise OllamaError(
                "Model '{}' is not available locally.".format(model),
                status_code=404,
                hint="Download it once with `ollama pull {}`.".format(model),
            )
        raise OllamaError(
            "Ollama returned {}: {}".format(response.status_code, body[:500]),
            status_code=502,
        )

    # -- read-only endpoints ----------------------------------------------
    async def version(self) -> str:
        try:
            response = await self.client.get("/api/version")
            response.raise_for_status()
            return response.json().get("version", "unknown")
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise self._unreachable(exc)
        except httpx.HTTPError as exc:
            raise OllamaError("Failed to read Ollama version: {}".format(exc))

    async def list_models(self) -> List[Dict[str, Any]]:
        try:
            response = await self.client.get("/api/tags")
            response.raise_for_status()
            return response.json().get("models", []) or []
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise self._unreachable(exc)
        except httpx.HTTPError as exc:
            raise OllamaError("Failed to list Ollama models: {}".format(exc))

    # -- embeddings --------------------------------------------------------
    async def embed(
        self, inputs: List[str], model: Optional[str] = None
    ) -> List[List[float]]:
        """Embed a batch of strings with the retrieval model.

        Ollama's /api/embed takes a list and returns vectors in the same order,
        so ingestion sends batches rather than paying HTTP overhead per chunk.
        The embedding model is a different model from the chat one, and asking
        for it keeps it resident alongside -- both are small enough that this
        is cheaper than reloading either.
        """
        if not inputs:
            return []
        target = model or settings.rag_embedding_model
        try:
            response = await self.client.post(
                "/api/embed",
                json={"model": target, "input": inputs, "keep_alive": _keep_alive()},
            )
            self._raise_for_response(response, target)
            vectors = response.json().get("embeddings") or []
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise self._unreachable(exc)
        except httpx.HTTPError as exc:
            raise OllamaError("Embedding request failed: {}".format(exc))

        if len(vectors) != len(inputs):
            raise OllamaError(
                "Ollama returned {} embeddings for {} inputs.".format(
                    len(vectors), len(inputs)
                )
            )
        return vectors

    # -- chat --------------------------------------------------------------
    def _payload(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        stream: bool,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model or settings.ollama_model,
            "messages": messages,
            "stream": stream,
            # Keep the model loaded between turns; a cold reload on a 4 GB CPU is
            # ~10-20s and Ollama otherwise unloads after 5 min idle.
            "keep_alive": _keep_alive(),
            "options": {
                "temperature": (
                    settings.temperature if temperature is None else temperature
                ),
                "num_predict": settings.max_tokens if max_tokens is None else max_tokens,
                "num_ctx": settings.num_ctx,
                # Stops a small model looping a phrase, which it does badly in
                # Hindi; Ollama's own defaults (1.1 / 64) are too weak here.
                "repeat_penalty": settings.repeat_penalty,
                "repeat_last_n": settings.repeat_last_n,
            },
        }
        if response_format is not None:
            # Ollama constrains decoding to this JSON schema -- essential for
            # getting reliable structured output out of a 1.5B model.
            payload["format"] = response_format
        return payload

    async def warm(self, model: Optional[str] = None) -> Dict[str, Any]:
        """Load the model into memory without generating anything.

        An empty `messages` list makes Ollama load the weights and return
        straight away (`done_reason: "load"`), so this costs the load time and
        no decoding at all.

        `num_ctx` has to match what real requests send: Ollama keys a resident
        model by its options, so warming at one context size and then asking at
        another silently reloads the model and wastes the whole exercise.
        """
        payload: Dict[str, Any] = {
            "model": model or settings.ollama_model,
            "messages": [],
            "keep_alive": _keep_alive(),
            "options": {"num_ctx": settings.num_ctx},
        }
        try:
            response = await self.client.post("/api/chat", json=payload)
            self._raise_for_response(response, payload["model"])
            return response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise self._unreachable(exc)
        except httpx.HTTPError as exc:
            raise OllamaError("Failed to warm the model: {}".format(exc))

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Single-shot completion. Returns the raw Ollama response body."""
        payload = self._payload(
            messages, model, temperature, max_tokens, False, response_format
        )
        try:
            response = await self.client.post("/api/chat", json=payload)
            self._raise_for_response(response, payload["model"])
            return response.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise self._unreachable(exc)
        except httpx.ReadTimeout:
            raise OllamaError(
                "The model did not respond within {}s.".format(
                    settings.ollama_timeout_seconds
                ),
                status_code=504,
                hint="Lower max_tokens, or wait for the first request to warm the model.",
            )
        except httpx.HTTPError as exc:
            raise OllamaError("Chat request failed: {}".format(exc))

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Yield each decoded chunk from Ollama's newline-delimited JSON stream."""
        payload = self._payload(messages, model, temperature, max_tokens, True)
        try:
            async with self.client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code >= 400:
                    await response.aread()
                    self._raise_for_response(response, payload["model"])
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed stream line: %s", line[:200])
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise self._unreachable(exc)
        except httpx.ReadTimeout:
            raise OllamaError(
                "The stream timed out after {}s.".format(settings.ollama_timeout_seconds),
                status_code=504,
            )


def build_usage(response: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise Ollama's nanosecond timings into a frontend-friendly shape.

    The prefill/decode split is carried through rather than folded into
    `total_duration_ms`, because on CPU the two answer to opposite levers.
    Prefill is charged per token of context, so it is where retrieval's real
    latency cost lands -- four textbook passages are read in full before the
    first token appears. Decode is charged per token produced, so it answers to
    max_tokens and to how wordy the persona is. Summed together they say a turn
    was slow; apart they say which change made it slow.
    """
    eval_count = response.get("eval_count") or 0
    eval_duration_ns = response.get("eval_duration") or 0
    tps = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns else 0.0
    return {
        "prompt_tokens": response.get("prompt_eval_count") or 0,
        "completion_tokens": eval_count,
        "total_duration_ms": int((response.get("total_duration") or 0) / 1e6),
        "load_duration_ms": int((response.get("load_duration") or 0) / 1e6),
        "tokens_per_second": round(tps, 2),
        "prompt_eval_ms": int((response.get("prompt_eval_duration") or 0) / 1e6),
        "eval_ms": int(eval_duration_ns / 1e6),
    }


# Single shared client for the app; its lifecycle is bound to the FastAPI
# lifespan in app/main.py so connections are pooled and reused.
client = OllamaClient()
