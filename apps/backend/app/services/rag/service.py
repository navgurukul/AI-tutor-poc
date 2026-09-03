"""Process-wide handles for the library, plus the status the API reports.

Opening the store can fail for a reason the user can fix (a Python without
SQLite extension support, a corpus built with a different embedding model), and
that reason has to survive as far as the UI. So the failure is captured here
once at startup instead of being raised from every request.
"""

import logging
from typing import Any, Dict

from app.config import settings
from app.services.rag.ingest import IngestionService
from app.services.rag.reembed import ReembedService
from app.services.rag.store import LibraryStore, StoreUnavailable

logger = logging.getLogger(__name__)

store = LibraryStore(
    db_path=settings.rag_db_path,
    dims=settings.rag_embedding_dims,
    embedding_model=settings.rag_embedding_model,
)
ingestion = IngestionService(store)
reembedding = ReembedService(store)


def open_store() -> None:
    """Open the library, or record why it could not be opened.

    Deliberately does not raise: retrieval is an enhancement, and a backend
    that refuses to start because the textbook library is missing would be a
    worse product than one that answers from the model alone.
    """
    if not settings.rag_enabled:
        logger.info("Retrieval disabled by configuration (rag_enabled=false).")
        return
    try:
        store.open()
    except StoreUnavailable as exc:
        store.unavailable_reason = exc
        logger.warning(
            "Textbook retrieval unavailable: %s%s",
            exc.detail,
            " ({})".format(exc.hint) if exc.hint else "",
        )


def close_store() -> None:
    store.close()


def status() -> Dict[str, Any]:
    """Library status for /health and the setup page."""
    if not settings.rag_enabled:
        return {"enabled": False, "available": False, "reason": "Disabled by configuration."}
    if not store.is_open:
        reason = store.unavailable_reason
        return {
            "enabled": True,
            "available": False,
            "reason": reason.detail if reason else "Not opened.",
            "hint": reason.hint if reason else None,
        }
    return {
        "enabled": True,
        "available": True,
        "embedding_model": store.embedding_model,
        "dims": store.dims,
        "vector_table": store.vector_table,
        "documents": store.document_count(),
        "chunks": store.chunk_count(),
        "db_path": str(store.db_path),
        "coverage": store.coverage(),
    }
