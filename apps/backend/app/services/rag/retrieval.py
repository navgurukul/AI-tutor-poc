"""Query-time retrieval and the prompt block it produces."""

import logging
from typing import List, Optional

from app.config import settings
from app.services.rag.embeddings import embed_query
from app.services.rag.store import LibraryStore, Retrieved, StoreUnavailable

logger = logging.getLogger(__name__)


async def retrieve(
    store: LibraryStore,
    question: str,
    *,
    grade: Optional[int],
    subject: Optional[str],
    k: Optional[int] = None,
) -> List[Retrieved]:
    """Nearest textbook chunks for a question, or [] if retrieval can't run.

    Never raises: a tutor that answers from the model alone is a working tutor,
    whereas one that 500s because the library is missing is not. Failures are
    logged and the caller carries on without context.
    """
    if not settings.rag_enabled or not store.is_open or not question.strip():
        return []
    try:
        vector = await embed_query(question)
        limit = k or settings.rag_top_k
        hits = store.search(
            vector,
            grade=grade,
            subject=subject,
            k=limit,
            max_distance=settings.rag_max_distance,
        )
        if not hits and subject:
            # The session's subject is a label picked in the UI; the library's is
            # whatever the person ingesting the PDF typed. When the two disagree
            # -- "Mathematics" selected against a book filed as "Science" -- an
            # exact filter hides a library that does contain the answer, and the
            # tutor looks like it never read the book. Retry across the student's
            # own grade and let the distance threshold judge relevance.
            hits = store.search(
                vector,
                grade=grade,
                subject=None,
                k=limit,
                max_distance=settings.rag_max_distance,
            )
            if hits:
                logger.info(
                    "No %s passage matched; used other subjects in grade %s.",
                    subject,
                    grade,
                )
        return hits
    except StoreUnavailable as exc:
        logger.warning("Retrieval skipped: %s", exc.detail)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Retrieval failed, answering without context: %s", exc)
    return []


def build_context_block(hits: List[Retrieved]) -> str:
    """Format retrieved chunks for the prompt.

    Each excerpt is labelled with its source so the model can point a student
    at the page, and the instruction is deliberately permissive: a 1.5B model
    told to answer *only* from context refuses far too often, which reads to a
    student as the tutor being broken.
    """
    if not hits:
        return ""

    # Trim from the end until the budget is met. Hits arrive best-first, so a
    # question whose top passage alone exceeds the budget still gets that
    # passage -- an over-long excerpt is better than none, and the cap exists
    # to stop the tail, not the head.
    budget = settings.rag_context_max_chars
    kept: List[Retrieved] = []
    used = 0
    for hit in hits:
        if kept and used + len(hit.text) > budget:
            break
        kept.append(hit)
        used += len(hit.text)
    hits = kept

    parts = []
    for index, hit in enumerate(hits, start=1):
        pages = (
            "p. {}".format(hit.page_start)
            if hit.page_start == hit.page_end
            else "pp. {}-{}".format(hit.page_start, hit.page_end)
        )
        label = " - ".join(filter(None, [hit.document_title, hit.heading, pages]))
        parts.append("[{}] {}\n{}".format(index, label, hit.text))
    return (
        "Here are excerpts from the student's own textbook. Prefer them over your "
        "own knowledge where they apply, and use their wording and examples. If "
        "they do not cover the question, answer normally without mentioning them.\n\n"
        + "\n\n".join(parts)
    )


def citations(hits: List[Retrieved]) -> List[dict]:
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
