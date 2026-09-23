"""
Unicode script primitives shared across the pipeline.

Every other module asks *this* module what script a character
belongs to, so that "is this Devanagari?" has exactly one answer
in the codebase.
"""

from typing import Any


# Unicode blocks we care about in the current EN / HI / PA phase.
DEVANAGARI = ("ऀ", "ॿ")
GURMUKHI = ("਀", "੿")

# Devanagari sub-ranges used by the legacy converter.
DEV_CONSONANTS = ("क", "ह")          # क .. ह
DEV_NUKTA_CONSONANTS = ("क़", "य़")    # क़ .. य़
DEV_VOWEL_SIGNS = ("ा", "ौ")         # ा .. ौ
DEV_VIRAMA = "्"                          # ्
DEV_NUKTA = "़"                           # ़
DEV_I_MATRA = "ि"                         # ि
DEV_DANDA = "।"                           # ।
DEV_DOUBLE_DANDA = "॥"                    # ॥


def in_range(char: str, block: tuple[str, str]) -> bool:
    return block[0] <= char <= block[1]


def is_devanagari(char: str) -> bool:
    return in_range(char, DEVANAGARI)


def is_gurmukhi(char: str) -> bool:
    return in_range(char, GURMUKHI)


def is_dev_consonant(char: str) -> bool:
    """True for a base consonant that an i-matra may attach to."""
    return (
        in_range(char, DEV_CONSONANTS)
        or in_range(char, DEV_NUKTA_CONSONANTS)
    )


def is_dev_vowel_sign(char: str) -> bool:
    return in_range(char, DEV_VOWEL_SIGNS)


def text_stats(text: str) -> dict[str, int]:
    """
    Count characters by class.

    These are raw signals for the detector. They deliberately make
    no language claim: Devanagari characters mean "Devanagari
    script", not "Hindi".
    """
    stats = {
        "total_chars": len(text),
        "latin_chars": 0,
        "devanagari_chars": 0,
        "gurmukhi_chars": 0,
        "digits": 0,
        "spaces": 0,
        "punctuation": 0,
        "other_chars": 0,
    }

    for char in text:
        if "a" <= char.lower() <= "z":
            stats["latin_chars"] += 1
        elif is_devanagari(char):
            stats["devanagari_chars"] += 1
        elif is_gurmukhi(char):
            stats["gurmukhi_chars"] += 1
        elif char.isdigit():
            stats["digits"] += 1
        elif char.isspace():
            stats["spaces"] += 1
        elif char.isascii() and not char.isalnum():
            stats["punctuation"] += 1
        else:
            stats["other_chars"] += 1

    return stats


def merge_stats(parts: list[dict[str, int]]) -> dict[str, int]:
    """Sum page-level stats into a document-level total."""
    merged = {
        "total_chars": 0,
        "latin_chars": 0,
        "devanagari_chars": 0,
        "gurmukhi_chars": 0,
        "digits": 0,
        "spaces": 0,
        "punctuation": 0,
        "other_chars": 0,
    }
    for part in parts:
        for key in merged:
            merged[key] += part.get(key, 0)
    return merged


def ratios(stats: dict[str, Any]) -> dict[str, float]:
    """
    Script ratios over the *complete* extracted text.

    Spaces and punctuation stay in the denominator on purpose, so a
    ratio describes the page as it actually is rather than an
    alphabet-only subset.
    """
    total = stats.get("total_chars", 0)
    if total == 0:
        return {
            "latin_ratio": 0.0,
            "devanagari_ratio": 0.0,
            "gurmukhi_ratio": 0.0,
        }

    return {
        "latin_ratio": round(stats.get("latin_chars", 0) / total, 4),
        "devanagari_ratio": round(stats.get("devanagari_chars", 0) / total, 4),
        "gurmukhi_ratio": round(stats.get("gurmukhi_chars", 0) / total, 4),
    }


def dominant_script(stats: dict[str, Any], min_chars: int = 10) -> str:
    """
    Pick a script from actual Unicode evidence.

    Conservative by design: below `min_chars` of everything we say
    "Unknown" rather than guessing from a handful of characters.
    """
    candidates = {
        "Devanagari": stats.get("devanagari_chars", 0),
        "Gurmukhi": stats.get("gurmukhi_chars", 0),
        "Latin": stats.get("latin_chars", 0),
    }

    best = max(candidates, key=lambda name: candidates[name])

    if candidates[best] < min_chars:
        return "Unknown"

    return best


# Token estimation is deliberately NOT defined here.
#
# It is delegated to `app.services.rag.query.estimate_tokens`, which is the
# same function `retrieval.trim_passage` and `retrieval.fit_to_budget` use to
# decide what actually reaches the model. That identity is the whole point of
# this port: the chunker aims at `rag_chunk_target_tokens` so that a chunk
# arrives at the prompt WHOLE, and "90 tokens" has to mean the same number at
# both ends or the sizing silently misses.
#
# The upstream version of this module had its own estimator at 2.2 characters
# per token for Devanagari against the app's 1.2, so a chunk built to "260
# tokens" measured 477 by the time the prompt budget looked at it -- which is
# exactly the mismatch that left 83% of the library undeliverable.
from app.services.rag.query import estimate_tokens  # noqa: F401  (re-export)
