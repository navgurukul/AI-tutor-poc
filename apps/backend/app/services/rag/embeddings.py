"""Query and document embeddings, via the local Ollama daemon.

nomic-embed-text is trained with task prefixes, and they are not decoration:
the model puts questions and passages in deliberately different places, so a
question embedded as though it were a passage lands in the wrong neighbourhood.
Retrieval quality drops noticeably without them, and nothing errors -- results
just get quietly worse, which is why this is centralised here rather than left
to each caller to remember.
"""

import logging
from typing import List, Sequence

from app.config import settings
from app.services.ollama_client import OllamaError, client

logger = logging.getLogger(__name__)

_QUERY_PREFIX = "search_query: "
_DOCUMENT_PREFIX = "search_document: "


def _needs_prefix(model: str) -> bool:
    """Only the nomic family uses these prefixes; others would embed them as text."""
    return "nomic" in model.lower()


async def embed_documents(texts: Sequence[str]) -> List[List[float]]:
    model = settings.rag_embedding_model
    prepared = (
        [_DOCUMENT_PREFIX + t for t in texts] if _needs_prefix(model) else list(texts)
    )
    return await client.embed(prepared, model=model)


async def embed_query(text: str) -> List[float]:
    model = settings.rag_embedding_model
    prepared = _QUERY_PREFIX + text if _needs_prefix(model) else text
    vectors = await client.embed([prepared], model=model)
    if not vectors:
        raise OllamaError("Embedding model returned no vector for the query.")
    return vectors[0]
