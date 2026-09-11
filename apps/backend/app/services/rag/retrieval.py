"""Query-time retrieval and the prompt block it produces."""

import logging
import re
from collections import Counter
from dataclasses import replace
from typing import Dict, List, Optional, Set

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


# -- shortening a passage to the question --------------------------------

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z]+")
# A Class 6 textbook defines a term as "this dark part is called the shadow".
# Most of the benchmark's answer-key phrases are sentences of exactly that
# shape, so one that also matches the question is worth a little extra.
_DEFINES = re.compile(r"\b(?:called|known as|defined as|means)\b", re.IGNORECASE)
_ELLIPSIS = "\u2026"
# Three letters and up; anything shorter is dropped before this is consulted.
_STOPWORDS = frozenset(
    """
    about after again all also and any are because been before being between
    both but can could did does doing done down during each few for from had
    has have having her here his how into its just may more most much must
    not now off once only other our out over own same she should some such
    than that the their them then there these they this those through too
    under until very was were what when where which while who whom why will
    with would you your
    """.split()
)


def _stems(text: str) -> Set[str]:
    """Crude stems: lowercase words of three letters or more, stop words out,
    a plural "s" dropped, the rest cut to five letters.

    Five letters joins "vibrate" and "vibration", "sublimate" and
    "sublimation", "friction" and "frictional" -- all pairs suffix-stripping
    gets wrong. The occasional false match only raises a sentence's score; it
    can never remove text from a passage.
    """
    stems = set()
    for word in _WORD.findall(text.lower()):
        if len(word) < 3 or word in _STOPWORDS:
            continue
        if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
            word = word[:-1]
        stems.add(word[:5])
    return stems


def _pieces(sentence: str, size: int) -> List[str]:
    """A "sentence" longer than a window, split on spaces into `size` parts.

    Extracted tables and exercise pages run for a thousand characters without
    a full stop; unsplit, they could never fit in a window at all.
    """
    pieces: List[str] = []
    current = ""
    for word in sentence.split(" "):
        while len(word) > size:  # a run with no space to break at
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:size])
            word = word[size:]
        if current and len(current) + 1 + len(word) > size:
            pieces.append(current)
            current = word
        else:
            current = "{} {}".format(current, word) if current else word
    if current:
        pieces.append(current)
    return pieces


def shorten_passage(text: str, query: str, limit: Optional[int] = None) -> str:
    """The passage, or if it is longer than rag_passage_max_chars, the run of
    consecutive sentences in it that best answers the question.

    The budget never trims the top passage, so on its own it cannot bound a
    turn: in exp006 all 8 turns still over 6s at 800 characters were ONE
    passage of 950-1,200 characters -- an exercise page, a planet table, an
    activity with the definition at its end -- read in full at ~25ms a token.
    This is what bounds them.

    Anchors on the sentence that matches the question most distinctively,
    then keeps the sentence before it, then what follows, then -- room
    permitting -- what precedes:

      * distinctively, not most often: a question word counts 1/N for a word
        the passage uses in N sentences. The sweat passage says "skin" seven
        times in its opening about hair, nails and touch; counted plainly,
        that opening outscored "then sweat is released. It helps to reduce
        the temperature of the body", which is the answer to "why".
      * a matching sentence that defines a term ("this dark part is called the
        shadow") scores extra -- it is how this textbook states answers.
      * the sentence before, because a definition leans on it ("That part
        remains dark.") and would otherwise begin with a dangling "this".
      * what follows before what precedes, because an explanation comes after
        the sentence that names its subject ("How is paper made ?" and then
        the steps).

    A passage that matches nothing keeps its opening. Cut ends are marked
    with an ellipsis so the model can tell it has an excerpt. Lexical on
    purpose: embedding every sentence would put an Ollama call into each
    turn, which is the one cost this exists to remove. A passage that
    already fits comes back byte-for-byte unchanged.
    """
    limit = settings.rag_passage_max_chars if limit is None else limit
    if not limit or len(text) <= limit:
        return text
    flat = " ".join(text.split())
    if len(flat) <= limit:
        # Only the PDF's hard line wraps were over; the words all fit.
        return flat

    # Room for an ellipsis at each end, so the result never exceeds `limit`.
    room = limit - 2 * (len(_ELLIPSIS) + 1)
    sentences: List[str] = []
    for sentence in _SENTENCE_END.split(flat):
        sentences.extend(
            [sentence] if len(sentence) <= room else _pieces(sentence, (room - 1) // 2)
        )

    wanted = _stems(query)
    matched = [_stems(sentence) & wanted for sentence in sentences]
    spread = Counter(stem for found in matched for stem in found)
    score = [
        sum(1.0 / spread[stem] for stem in found)
        + (0.5 if found and _DEFINES.search(sentence) else 0.0)
        for sentence, found in zip(sentences, matched)
    ]
    anchor = max(range(len(sentences)), key=lambda i: (score[i], -i))

    start, end = anchor, anchor + 1
    used = len(sentences[anchor])

    def fits(i: int) -> bool:
        return used + 1 + len(sentences[i]) <= room

    if start > 0 and fits(start - 1):
        start -= 1
        used += 1 + len(sentences[start])
    while end < len(sentences) and fits(end):
        used += 1 + len(sentences[end])
        end += 1
    while start > 0 and fits(start - 1):
        start -= 1
        used += 1 + len(sentences[start])

    return (
        (_ELLIPSIS + " " if start > 0 else "")
        + " ".join(sentences[start:end])
        + (" " + _ELLIPSIS if end < len(sentences) else "")
    )


def prompt_hits(
    hits: List[Retrieved],
    query: str = "",
    budget: Optional[int] = None,
    reuse: Optional[Dict[int, str]] = None,
) -> List[Retrieved]:
    """The passages a turn actually sends: each shortened to the question,
    then packed into the character budget. Text is the shortened text.

    `reuse` maps a chunk id to the text a previous turn sent for that passage,
    and a passage found there goes out again word for word instead of being
    re-shortened around the new question. That is not tidiness: Ollama only
    reuses its cache when this turn's prompt starts with the last one, and a
    follow-up that retrieves its topic question's passage is how most
    follow-ups on the target got to first token in 0.6-1.7s (exp006). Cut
    around "how can we reduce it?" instead of "what is frictional force?",
    the same passage becomes a different string and that turn pays full
    prefill again.
    """
    reuse = reuse or {}
    shortened = [
        replace(hit, text=reuse.get(hit.chunk_id) or shorten_passage(hit.text, query))
        for hit in hits
    ]
    return within_budget(shortened, budget)


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
    listed as a source. prompt_hits runs this on passages already shortened
    to rag_passage_max_chars, so the "always kept" top passage is bounded too.

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
    hits: List[Retrieved],
    budget: Optional[int] = None,
    query: str = "",
    reuse: Optional[Dict[int, str]] = None,
) -> str:
    """The excerpt block for these hits: shortened, budgeted and labelled."""
    return format_excerpts(prompt_hits(hits, query, budget, reuse))


def format_excerpts(hits: List[Retrieved]) -> str:
    """Format the passages a turn sends (see prompt_hits) for the prompt.

    Excerpts only. What to do with them is EXCERPT_PREAMBLE in
    app.services.tutor, which the prompt build places directly above this
    block -- keeping the instruction there means it stays with the persona and
    the style rule rather than being repeated per retrieval.

    Each excerpt is labelled with its source so the model can point a student
    at the page.
    """
    if not hits:
        return ""

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
