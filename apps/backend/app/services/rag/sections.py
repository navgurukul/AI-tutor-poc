"""rag-engine/src/section-resolver.ts

Resolves "what's in chapter 3", "explain 3.1", "tell me about photosynthesis"
to a chapter/topic/subtopic detected at ingest, so the caller can return the
whole section instead of the top-K fragments.
"""

import re
from typing import List, Optional, Set

from app.services.rag.models import SectionInfo

_STOPWORDS = frozenset(
    "the a an of in on to and or for about what is are me my tell explain chapter "
    "unit topic section subtopic everything know all from this that can you please "
    "give summary summarize".split()
)
_LEVEL_RANK = {"subtopic": 3, "topic": 2, "chapter": 1}
_LEVEL_KEYWORD = re.compile(r"\b(chapter|unit)\s*(\d+)\b", re.IGNORECASE)
_DOTTED_NUM = re.compile(r"\b(\d+\.\d+(?:\.\d+)?)\b")
_CONFIDENCE_THRESHOLD = 0.6


def _significant_words(text: str) -> List[str]:
    cleaned = re.sub(r"[^a-z0-9.\s]", " ", text.lower())
    return [w for w in cleaned.split() if len(w) > 2 and w not in _STOPWORDS]


def _overlap_score(query_words: Set[str], title_words: List[str]) -> float:
    if not title_words:
        return 0.0
    return sum(1 for w in title_words if w in query_words) / len(title_words)


def resolve_section(query: str, sections: List[SectionInfo]) -> Optional[SectionInfo]:
    if not sections:
        return None

    level_match = _LEVEL_KEYWORD.search(query)
    if level_match:
        number = level_match.group(2)
        pattern = re.compile(r"^(chapter|unit)\s+0*{}\b".format(number), re.IGNORECASE)
        for section in sections:
            if section.level == "chapter" and pattern.search(section.title or ""):
                return section

    dotted = _DOTTED_NUM.search(query)
    if dotted:
        number = dotted.group(1)
        level = "subtopic" if len(number.split(".")) >= 3 else "topic"
        for section in sections:
            if section.level == level and (section.title or "").startswith(number):
                return section

    query_words = _significant_words(query)
    if not query_words:
        return None
    wanted = set(query_words)

    best: Optional[SectionInfo] = None
    best_score = 0.0
    for section in sections:
        score = _overlap_score(wanted, _significant_words(section.title or ""))
        if score > best_score or (
            score == best_score
            and score > 0
            and best is not None
            and _LEVEL_RANK[section.level] > _LEVEL_RANK[best.level]
        ):
            best_score = score
            best = section
    return best if best_score >= _CONFIDENCE_THRESHOLD else None
