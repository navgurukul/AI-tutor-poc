"""Deciding whether the library actually answers the question.

A single global distance threshold cannot work across languages, because the
distance scale itself shifts with the query language. With bge-m3 a *correct*
hit sits at distance 0.21 for an English question and 0.51 for a Hindi question
against the same English page. A cut-off of 0.42 tuned on English therefore
discards the Hindi student's correct answer before the model ever sees it --
silently, and only for the students who most need the feature.

Two mechanisms replace the one constant:

  - a **relative gate**: keep hits within +0.12 of the best hit. This
    normalises the language offset away, because every candidate for one query
    shares that query's language and so shares the offset.

  - a **per-query-language ceiling**: reject everything when even the best hit
    is too far. This is what lets the tutor say nothing at all.

The relative gate alone cannot abstain -- there is always a best hit, and
everything near it survives. The ceiling alone cannot handle the language
shift. Both are needed.
"""

import logging
import re
from typing import List, Optional, Sequence, Tuple

from app.config import settings
from app.services.rag.store import Retrieved

logger = logging.getLogger(__name__)

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")

# Romanized Indic typed in Latin script -- "utak kya hai", "manav shareer".
# This is the most common typed input in this market and the case a script
# sniffer gets exactly wrong: it reads as English, takes the strictest ceiling,
# and throws away a correct hit sitting at 0.51.
_ROMANIZED_MARKERS = {
    "kya", "hai", "hain", "kaise", "kyun", "kyon", "kaun", "kahan", "kab",
    "batao", "samjhao", "matlab", "arth", "prakar", "udaharan", "karya",
    "ka", "ki", "ke", "mein", "aur", "nahi", "hota", "hoti", "kare", "karta",
    "shareer", "sharir", "koshika", "utak", "paudha", "jeev",
}

# Language codes the ceilings are keyed by. Hindi and Marathi share Devanagari
# and currently share a ceiling; they are kept separate so that measuring them
# apart later is a config change, not a code change.
EN = "en"
HI = "hi"
MR = "mr"
ROMANIZED = "romanized"

_NAME_TO_CODE = {
    "english": EN,
    "hindi": HI,
    "marathi": MR,
}


def _ceilings() -> dict:
    return {
        EN: settings.rag_ceiling_en,
        HI: settings.rag_ceiling_hi,
        MR: settings.rag_ceiling_mr,
        ROMANIZED: settings.rag_ceiling_romanized,
    }


def sniff_language(text: str) -> Tuple[str, bool]:
    """Guess a query language from the text. Returns (code, confident).

    Only ever a fallback. Script detection cannot separate Hindi from Marathi
    -- they share Devanagari -- and it cannot recognise romanized Indic at all
    without help, which is what the marker list is for.
    """
    if not text or not text.strip():
        return EN, False
    if _DEVANAGARI.search(text):
        # Devanagari, but Hindi or Marathi? Nothing in the script says. Return
        # the shared ceiling and admit the uncertainty.
        return HI, False
    words = {w.strip(".,?!\"'").lower() for w in text.split()}
    if words & _ROMANIZED_MARKERS:
        return ROMANIZED, True
    return EN, False


def resolve_query_language(session_language: Optional[str], question: str) -> str:
    """The language to judge this query in.

    From the session first -- the ASR selection or the UI toggle, both of which
    already know it. Sniffing is the fallback, and when the fallback is not
    confident it applies the *most permissive* ceiling rather than the
    strictest: a false accept costs one noisy passage, a false reject costs the
    entire answer and says nothing about why.
    """
    if session_language:
        code = _NAME_TO_CODE.get(session_language.strip().lower())
        if code is None and session_language.strip().lower() in _ceilings():
            code = session_language.strip().lower()
        if code is not None:
            # An English session whose text is plainly romanized Indic is the
            # one case worth overriding: the toggle says English because the
            # student never changed it, and the strictest ceiling is exactly
            # wrong for what they typed.
            if code == EN:
                sniffed, confident = sniff_language(question)
                if confident and sniffed == ROMANIZED:
                    return ROMANIZED
            return code

    sniffed, confident = sniff_language(question)
    if confident:
        return sniffed
    # Unsure: take the loosest ceiling of all, not the strictest.
    return max(_ceilings(), key=lambda code: _ceilings()[code])


def gate_dense_hits(
    hits: Sequence[Retrieved], language: str
) -> Tuple[List[Retrieved], float]:
    """Apply the ceiling, then the relative gate. Returns (survivors, ceiling).

    Order matters. The ceiling asks "is there an answer here at all?" and the
    relative gate asks "which of these belong with the best one?" -- run the
    other way round, a query with no good hits would still return a tight
    cluster of equally bad ones.
    """
    ceilings = _ceilings()
    ceiling = ceilings.get(language, max(ceilings.values()))
    if not hits:
        return [], ceiling

    if ceiling <= 0.0:
        # Retrieval is off for this bucket -- see rag_ceiling_romanized. Not a
        # tight threshold but a measured absence of signal.
        logger.info(
            "Retrieval disabled for query language %r; answering unaided.", language
        )
        return [], ceiling

    best = min(h.distance for h in hits)
    if best > ceiling:
        # Not even the closest passage is close enough. This is the branch that
        # lets the tutor answer unaided and cite nothing.
        return [], ceiling

    margin = settings.rag_relative_margin
    survivors = [h for h in hits if h.distance <= best + margin]
    logger.debug(
        "Gate (%s): best %.3f, ceiling %.2f, margin %.2f -> %d/%d survive",
        language, best, ceiling, margin, len(survivors), len(hits),
    )
    return survivors, ceiling
