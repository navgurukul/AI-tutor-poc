"""AFE-Learning-App's retrieval, ported from rag-engine/src/index.ts
(RagEngine.query, applyTokenBudget, buildContextBlock). Used by the chat turn
since stage 3 of the golden comparison; the older dense-only retrieval
(retrieval.py over library.db) still serves the Library page.

  0. a question that names a whole chapter/topic/subtopic gets ALL of it
  1. otherwise embed the question; dense (k=30) and BM25 (k=30) search
  2. fuse with RRF, keep the top K
  3. pull in each hit's neighbours (seq +-1), merge adjacent runs, dedupe overlap
  4. trim to a word-count token budget
"""

import logging
from typing import List, Optional

from app.config import settings
from app.services.rag.fusion import reciprocal_rank_fusion
from app.services.rag.merge import merge_adjacent_chunks
from app.services.rag.sections import resolve_section
from app.services.rag.index_store import IndexStore, StoreUnavailable
from app.services.rag.models import Chunk
from app.services.rag.embeddings import embed_query

logger = logging.getLogger(__name__)

store = IndexStore(
    settings.hybrid_index_path,
    dims=settings.rag_embedding_dims,
    embedding_model=settings.rag_embedding_model,
)


def open_store() -> None:
    """Open the index, or record why not. Never raises: a missing index
    degrades the tutor to model-only answers."""
    if not settings.rag_enabled:
        return
    try:
        store.open()
    except StoreUnavailable as exc:
        store.unavailable_reason = exc
        logger.warning("Textbook retrieval unavailable: %s%s", exc.detail, " ({})".format(exc.hint) if exc.hint else "")


def close_store() -> None:
    store.close()


def approx_tokens(text: str) -> int:
    """AFE's estimate: words / 0.75, rounded up."""
    words = len(text.split())
    return -(-words * 4 // 3)  # ceil(words / 0.75)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    words = text.split()
    max_words = int(max_tokens * 0.75)
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


def apply_token_budget(chunks: List[Chunk], max_tokens: int, max_chunk_tokens: int = 450) -> List[Chunk]:
    out: List[Chunk] = []
    used = 0
    for chunk in chunks:
        # Each chunk is capped first so one oversized chunk cannot swallow the budget.
        text = _truncate_to_tokens(chunk.text, max_chunk_tokens)
        tokens = approx_tokens(text)
        if used + tokens > max_tokens and out:
            break
        out.append(chunk if text == chunk.text else chunk.with_(text=text))
        used += tokens
    return out


def _expand_with_neighbors(chunks: List[Chunk]) -> List[Chunk]:
    known = {(c.doc_id, c.seq): c for c in chunks}
    needed = {}
    for c in chunks:
        wanted = needed.setdefault(c.doc_id, set())
        if c.seq > 0:
            wanted.add(c.seq - 1)
        wanted.add(c.seq + 1)
    result = list(chunks)
    for doc_id, seqs in needed.items():
        missing = sorted(s for s in seqs if (doc_id, s) not in known)
        if not missing:
            continue
        for neighbor in store.get_chunks_by_seqs(doc_id, missing):
            key = (doc_id, neighbor.seq)
            if key in known:
                continue
            known[key] = neighbor
            result.append(neighbor.with_(score=0.0, matched_via=[]))
    return result


def _query_by_section(text: str, max_section_tokens: int) -> Optional[List[Chunk]]:
    match = resolve_section(text, store.list_sections())
    if match is None:
        return None
    chunks = store.get_chunks_by_section(match.doc_id, match.level, match.id)
    if not chunks:
        return None
    merged = merge_adjacent_chunks([c.with_(score=1.0, matched_via=["section"]) for c in chunks])
    return apply_token_budget(merged, max_section_tokens)


async def query(
    text: str,
    top_k: Optional[int] = None,
    max_context_tokens: Optional[int] = None,
    max_section_tokens: Optional[int] = None,
    candidate_k: Optional[int] = None,
    max_chunk_tokens: Optional[int] = None,
) -> List[Chunk]:
    """Passages for a question, best first. [] when retrieval cannot run."""
    if not settings.rag_enabled or not store.is_open or not text.strip():
        return []
    top_k = top_k or settings.hybrid_top_k
    candidate_k = candidate_k or settings.hybrid_candidate_k
    try:
        by_section = _query_by_section(text, max_section_tokens or settings.hybrid_max_section_tokens)
        if by_section is not None:
            return by_section

        vector = await embed_query(text)
        lexical_ids = store.lexical_search(text, candidate_k)
        dense = store.dense_search(vector, candidate_k)
        distance = dict(dense)

        fused = reciprocal_rank_fusion(
            [[(i, "dense") for i, _ in dense], [(i, "lexical") for i in lexical_ids]]
        )
        top_ids = [f["id"] for f in fused[:top_k]]
        by_id = {f["id"]: f for f in fused}
        results = [
            c.with_(
                score=by_id[c.id]["score"],
                matched_via=list(by_id[c.id]["matched_via"]),
                distance=distance.get(c.id),
            )
            for c in store.get_chunks_by_ids(top_ids)
        ]
        results = merge_adjacent_chunks(_expand_with_neighbors(results))
        return apply_token_budget(
            results,
            max_context_tokens or settings.hybrid_max_context_tokens,
            max_chunk_tokens or settings.hybrid_max_chunk_tokens,
        )
    except StoreUnavailable as exc:
        logger.warning("Textbook retrieval skipped: %s", exc.detail)
    except Exception as exc:  # noqa: BLE001 - a tutor with no context still answers
        logger.warning("Textbook retrieval failed, answering without context: %s", exc)
    return []


def source_name(chunk: Chunk) -> str:
    raw = chunk.metadata.get("title") or chunk.metadata.get("source") or chunk.doc_id
    return raw[:-4] if isinstance(raw, str) and raw.lower().endswith(".pdf") else str(raw)


def breadcrumb(chunk: Chunk) -> str:
    return " > ".join(
        p for p in (chunk.metadata.get("chapterTitle"), chunk.metadata.get("topicTitle"), chunk.metadata.get("subtopicTitle")) if p
    )


def build_context_block(chunks: List[Chunk]) -> str:
    """`[n] Source - Breadcrumb\\n{text}` blocks, exactly as AFE's buildContextBlock."""
    parts = []
    for index, chunk in enumerate(chunks, start=1):
        crumb = breadcrumb(chunk)
        tag = "{} - {}".format(source_name(chunk), crumb) if crumb else source_name(chunk)
        parts.append("[{}] {}\n{}".format(index, tag, chunk.text))
    return "\n\n".join(parts)


def status() -> dict:
    """Index status for /health."""
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
        "embedding_model": settings.rag_embedding_model,
        "dims": settings.rag_embedding_dims,
        "documents": store.document_count(),
        "chunks": store.chunk_count(),
        "db_path": str(store.path),
    }
