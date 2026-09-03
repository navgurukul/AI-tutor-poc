"""Query-time retrieval: two legs, one gate, one fused list.

The shape, and why it is this shape:

The dense leg decides *whether* there is an answer. The lexical leg only
decides the order. That asymmetry is the whole design. A lexical match is
evidence of shared spelling, not of relevance -- BM25 will happily return fifty
passages for a question the library does not cover, and RRF will rank four of
them into the prompt with a chapter and page attached. An answer that is wrong
is a bad answer; an answer that is wrong and carries a citation to the
student's own textbook is a different category of failure.

So the gate sits on the dense leg *before* fusion. After RRF there are only
ranks -- the distances the gate needs are gone.
"""

import logging
from typing import Dict, List, Optional, Sequence, Tuple

from app.config import settings
from app.services.rag.embeddings import embed_query
from app.services.rag.gate import gate_dense_hits, resolve_query_language
from app.services.rag.query import build_match_query, estimate_tokens
from app.services.rag.store import LibraryStore, Retrieved, StoreUnavailable

logger = logging.getLogger(__name__)


def _rrf(
    legs: Sequence[Sequence[Retrieved]], k: int = 60
) -> List[Retrieved]:
    """Reciprocal Rank Fusion.

    Rank-based on purpose: BM25 scores and cosine distances have no common
    scale, and any attempt to normalise one onto the other is a tuning
    parameter that drifts the moment either model changes. Ranks need nothing.

    k=60 is the standard damping constant; it flattens the difference between
    rank 1 and rank 2 enough that a passage found by both legs outranks one
    found brilliantly by either.
    """
    scores: Dict[int, float] = {}
    best: Dict[int, Retrieved] = {}
    for leg in legs:
        for rank, hit in enumerate(leg, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
            # Keep whichever copy carries a real distance -- the lexical leg
            # fills 1.0 as a placeholder and never a measured one.
            if hit.chunk_id not in best or hit.distance < best[hit.chunk_id].distance:
                best[hit.chunk_id] = hit
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [best[cid] for cid, _ in ordered]


async def retrieve(
    store: LibraryStore,
    question: str,
    *,
    grade: Optional[int],
    subject: Optional[str] = None,
    k: Optional[int] = None,
    language: Optional[str] = None,
) -> List[Retrieved]:
    """The passages worth putting in front of the model, or [].

    Never raises. A tutor that answers from the model alone is a working
    tutor; one that 500s because the library is missing is not. `subject` is
    accepted and ignored -- it is already inside every vector via the
    breadcrumb, and filtering on it could only ever return fewer results.
    """
    if not settings.rag_enabled or not store.is_open or not question.strip():
        return []
    try:
        query_language = resolve_query_language(language, question)
        # The store's model, not config's: after a re-embed cutover they differ.
        vector = await embed_query(question, model=store.embedding_model)
        candidates = settings.rag_candidates

        dense = store.search(vector, grade=grade, subject=None, k=candidates)

        # The gate, before fusion. An empty dense leg here means the library
        # does not cover the question -- and BM25 is never consulted, because
        # it cannot tell the difference between coverage and coincidence.
        survivors, ceiling = gate_dense_hits(dense, query_language)
        if not survivors:
            logger.info(
                "Nothing cleared the %s gate (ceiling %.2f, best %.3f); "
                "answering unaided.",
                query_language,
                ceiling,
                dense[0].distance if dense else float("nan"),
            )
            return []

        match_query = build_match_query(question)
        lexical = (
            store.search_lexical(match_query, grade=grade, k=candidates)
            if match_query
            else []
        )

        # Only passages that cleared the gate themselves, or sit immediately
        # beside one that did, are eligible. That keeps a definition split
        # across a chunk boundary retrievable without letting an unrelated
        # lexical hit ride in on a good one.
        eligible = {h.chunk_id for h in survivors}
        for hit in survivors:
            eligible.update(store.neighbours(hit.chunk_id))
        lexical = [h for h in lexical if h.chunk_id in eligible]

        fused = _rrf([survivors, lexical], k=settings.rag_rrf_k)
        limit = k or settings.rag_top_k
        return fused[:limit]
    except StoreUnavailable as exc:
        logger.warning("Retrieval skipped: %s", exc.detail)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retrieval failed, answering without context: %s", exc)
    return []


def _label(hit: Retrieved) -> str:
    pages = (
        "p. {}".format(hit.page_start)
        if hit.page_start == hit.page_end
        else "pp. {}-{}".format(hit.page_start, hit.page_end)
    )
    return " - ".join(filter(None, [hit.document_title, hit.heading, pages]))


_PREAMBLE = (
    "Here are excerpts from the student's own textbook. Prefer them over your "
    "own knowledge where they apply, and use their wording and examples. If "
    "they do not cover the question, answer normally without mentioning them."
)


def fit_to_budget(
    hits: Sequence[Retrieved], token_budget: Optional[int] = None
) -> List[Retrieved]:
    """As many whole passages as the budget allows, in order.

    k falls before a passage is cut. Three whole passages beat four half ones:
    a truncated passage loses exactly the part the model needed to answer from,
    and does it silently. This is why the budget is in tokens and the chunk
    bounds are in characters -- 2,000 characters of Devanagari is roughly three
    times the tokens of 2,000 characters of English, so a character budget
    would fit four English passages and overrun on four Hindi ones.
    """
    budget = token_budget or settings.rag_context_token_budget
    used = estimate_tokens(_PREAMBLE)
    kept: List[Retrieved] = []
    for hit in hits:
        cost = estimate_tokens("[{}] {}\n{}".format(len(kept) + 1, _label(hit), hit.text))
        if kept and used + cost > budget:
            break
        # The first passage goes in even if it alone exceeds the budget: a
        # tutor with one over-long excerpt is better than one with none, and
        # num_ctx is sized for that case.
        used += cost
        kept.append(hit)
    if len(kept) < len(hits):
        logger.info(
            "Context budget %d tokens: kept %d of %d passages (~%d tokens).",
            budget, len(kept), len(hits), used,
        )
    return kept


def build_context_block(hits: Sequence[Retrieved]) -> str:
    """Format retrieved chunks for the prompt.

    Each excerpt is labelled with its source so the model can point a student
    at the page, and the instruction is deliberately permissive: a small model
    told to answer *only* from context refuses far too often, which reads to a
    student as the tutor being broken.
    """
    if not hits:
        return ""
    parts = [
        "[{}] {}\n{}".format(i, _label(h), h.text) for i, h in enumerate(hits, start=1)
    ]
    return _PREAMBLE + "\n\n" + "\n\n".join(parts)


def citations(hits: Sequence[Retrieved]) -> List[dict]:
    """Compact source list for the UI."""
    return [
        {
            "title": h.document_title,
            "heading": h.heading,
            "page_start": h.page_start,
            "page_end": h.page_end,
            "grade": h.grade,
            "subject": h.subject,
            "distance": round(h.distance, 4),
        }
        for h in hits
    ]
