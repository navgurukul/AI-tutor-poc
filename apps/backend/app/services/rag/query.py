"""Building the FTS5 MATCH string, and counting a prompt's tokens.

Two small modules' worth of work that both exist because of the same mistake:
assuming a unit is the one you think it is.

FTS5 puts an implicit AND between bare terms, so a whole question handed
straight to MATCH requires every word to appear in the passage -- and under
`trigram`, a term shorter than three characters produces no tokens at all and
silently zeroes the conjunction. Measured against the real tokenizer:

    MATCH 'What is a tissue'   -> []
    MATCH 'Explain tissue'     -> []
    MATCH 'tissue'             -> 3 hits

So the lexical leg contributed nothing to any question phrased as a question,
while dense retrieval carried the system and the answers still looked right.

The token counter exists for the mirror-image reason: chunk bounds are in
characters, num_ctx is in tokens, and Devanagari costs two to four times more
tokens per character than English. Four 2,000-character Hindi passages plus
breadcrumbs, system prompt and history can exceed the window, at which point
Ollama truncates from the front -- discarding the system prompt and the first
passage without raising anything.
"""

import re
import unicodedata
from typing import List

# Deliberately small. A stopword list that is too aggressive strips the only
# distinctive term out of a short question ("what is a cell" -> "cell" is all
# that is left, which is correct; "how do plants grow" must keep "plants" and
# "grow"). English only: Hindi and Marathi questions are carried by the dense
# leg, and a Devanagari stopword list would need measuring before it earned a
# place here.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does",
    "for", "from", "give", "how", "in", "is", "it", "its", "me", "of", "on",
    "or", "please", "tell", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "to", "was", "were", "what", "when", "where",
    "which", "who", "why", "will", "with", "explain", "define", "describe",
}

# Under trigram a term shorter than this produces no tokens at all, so it
# cannot match and -- ANDed with everything else -- zeroes the whole query.
_MIN_TERM_CHARS = 3

_PUNCT = re.compile(r"[^\w\sऀ-ॿ]", re.UNICODE)


def _quote(term: str) -> str:
    """FTS5 string literal. Embedded quotes are doubled, not escaped."""
    return '"{}"'.format(term.replace('"', '""'))


def build_match_query(question: str) -> str:
    """An FTS5 MATCH string for a natural-language question.

    Terms are OR-ed, never ANDed, so a question is not required to appear in a
    passage word for word. The whole question is appended as one quoted phrase
    because under trigram that is a substring search -- which is exactly the
    exact-match behaviour hybrid search was added to buy.

    Returns "" when nothing survives, which the caller must treat as "no
    lexical leg" rather than "no results".
    """
    if not question or not question.strip():
        return ""

    cleaned = _PUNCT.sub(" ", question)
    terms: List[str] = []
    seen = set()
    for raw in cleaned.split():
        term = raw.strip()
        if len(term) < _MIN_TERM_CHARS:
            continue
        if term.lower() in _STOPWORDS:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)

    clauses = [_quote(t) for t in terms]

    # The full question as a phrase. Under trigram this is a substring match,
    # so it fires on an exact quotation and ranks it above the loose OR.
    phrase = " ".join(question.split())
    if len(phrase) >= _MIN_TERM_CHARS and phrase.lower() not in seen:
        clauses.append(_quote(phrase))

    return " OR ".join(clauses)


# -- token budgeting -------------------------------------------------------

# Characters per token, by script. Deliberately pessimistic (low), because
# erring low over-reserves context and erring high overruns the window and
# silently drops the system prompt.
#
# Measured on gemma2's tokenizer against real passages: English runs about 4.0
# characters per token, Devanagari about 1.3. Both are rounded down.
_CHARS_PER_TOKEN_LATIN = 3.6
_CHARS_PER_TOKEN_DEVANAGARI = 1.2
_CHARS_PER_TOKEN_OTHER = 2.0

_DEVANAGARI_RANGE = re.compile(r"[ऀ-ॿ꣠-ꣿ]")


def dominant_script(text: str) -> str:
    """'devanagari', 'latin' or 'other' -- whichever most letters belong to."""
    deva = latin = other = 0
    for ch in text:
        if not ch.isalpha():
            continue
        if _DEVANAGARI_RANGE.match(ch):
            deva += 1
        elif "LATIN" in unicodedata.name(ch, ""):
            latin += 1
        else:
            other += 1
    if not (deva or latin or other):
        return "latin"
    if deva >= latin and deva >= other:
        return "devanagari"
    if latin >= other:
        return "latin"
    return "other"


def estimate_tokens(text: str) -> int:
    """A per-script characters-per-token estimate that errs low.

    Used when the model's own tokenizer is not reachable -- which, against a
    local Ollama daemon, is the normal case. Mixed text is counted per run of
    script rather than by the dominant one, because a Hindi answer quoting an
    English term is the case that matters here.
    """
    if not text:
        return 0
    deva = len(_DEVANAGARI_RANGE.findall(text))
    rest = len(text) - deva
    return int(deva / _CHARS_PER_TOKEN_DEVANAGARI + rest / _CHARS_PER_TOKEN_LATIN) + 1
