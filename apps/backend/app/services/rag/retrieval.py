"""Query-time retrieval and the prompt block it produces."""

import logging
from typing import List, Optional

from app.config import settings
from app.services.rag.embeddings import embed_query
from app.services.rag.followup import embedding_text
from app.services.rag.store import LibraryStore, Retrieved, StoreUnavailable

logger = logging.getLogger(__name__)


def retrieval_query(question: str, previous_question: Optional[str]) -> str:
    """The text actually searched for: the question, or for a pronoun
    follow-up, the previous question and then it.

    One function for both callers -- the chat turn and the library search the
    benchmark scores against -- so what the benchmark measures is what a
    student's turn does.
    """
    if not settings.rag_carry_followups:
        return question
    return embedding_text(question, previous_question)


async def retrieve(
    store: LibraryStore,
    question: str,
    *,
    grade: Optional[int],
    subject: Optional[str],
    k: Optional[int] = None,
    previous_question: Optional[str] = None,
) -> List[Retrieved]:
    """Nearest textbook chunks for a question, or [] if retrieval can't run.

    Never raises: a tutor that answers from the model alone is a working tutor,
    whereas one that 500s because the library is missing is not. Failures are
    logged and the caller carries on without context.
    """
    if not settings.rag_enabled or not store.is_open or not question.strip():
        return []
    try:
        vector = await embed_query(retrieval_query(question, previous_question))
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


def within_budget(
    hits: List[Retrieved], budget: Optional[int] = None
) -> List[Retrieved]:
    """The leading hits that fit rag_context_max_chars -- what the model reads.

    Trimmed from the end until the budget is met. Hits arrive best-first, so a
    question whose top passage alone exceeds the budget still gets that
    passage -- an over-long excerpt is better than none, and the cap exists
    to stop the tail, not the head.

    This regularly drops the second of two retrieved passages: in exp004, 9 of
    the 20 turns that retrieved anything lost their #2 here, including the
    magnet-pole definition, behind a 1,193-character exercise page. The
    citations are built from the untrimmed hits, so a cut passage is still
    listed as a source.

    `budget` overrides the setting for one turn -- benchmark.py sweeps it per
    request so every arm shares one warm model and one prompt cache.
    """
    budget = budget or settings.rag_context_max_chars
    kept: List[Retrieved] = []
    used = 0
    for hit in hits:
        if kept and used + len(hit.text) > budget:
            break
        kept.append(hit)
        used += len(hit.text)
    return kept


def build_context_block(
    hits: List[Retrieved], budget: Optional[int] = None
) -> str:
    """Format retrieved chunks for the prompt.

    Excerpts only. What to do with them is EXCERPT_PREAMBLE in
    app.services.tutor, which the prompt build places directly above this
    block -- keeping the instruction there means it stays with the persona and
    the style rule rather than being repeated per retrieval.

    Each excerpt is labelled with its source so the model can point a student
    at the page.
    """
    if not hits:
        return ""

    hits = within_budget(hits, budget)

    parts = []
    for index, hit in enumerate(hits, start=1):
        pages = (
            "p. {}".format(hit.page_start)
            if hit.page_start == hit.page_end
            else "pp. {}-{}".format(hit.page_start, hit.page_end)
        )
        label = " - ".join(filter(None, [hit.document_title, hit.heading, pages]))
        parts.append("[{}] {}\n{}".format(index, label, hit.text))
    return "\n\n".join(parts)


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
