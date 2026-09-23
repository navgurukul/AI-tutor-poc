"""
Stage 8 -- quality validation.

The gate between "we produced text" and "we will answer students
from this text". Anything that fails here is kept in the report but
never embedded: an unusable chunk in the index is worse than a
missing one, because retrieval will surface it confidently.

Each issue names what is wrong so a failing corpus can be fixed
rather than merely re-run.
"""

from __future__ import annotations

import re
from typing import Any

from .chunk import MAX_TOKENS, MIN_TOKENS
from .model import Chunk
from .scripts import text_stats

# A chunk may exceed the chunker's ceiling slightly through overlap.
HARD_MAX_TOKENS = int(MAX_TOKENS * 1.25)

# Below this share of letters, the text is mostly symbols or noise.
MIN_LETTER_RATIO = 0.35

# Runs of a repeated character longer than this signal a broken
# extraction (dot leaders in a table of contents, ruled lines).
_REPEAT_RUN = re.compile(r"(.)\1{9,}")

# Share of whitespace-separated tokens that may be a single
# character before the text is treated as fragments rather than
# words.
#
# This is the signal that catches a PDF whose embedded font has no
# usable character map. Such a file still yields "text" -- it is
# just the wrong characters, shattered into singletons like
#     " > -66 &:,' &) 6 &0!!! # "! 6&0!
# which passes a letter-count check comfortably and then sits in
# the index as unsearchable noise.
#
# Measured over this corpus: real prose runs at a median of 0.01
# and a 99th percentile of 0.19, while a broken extraction has a
# median of 0.32. 0.25 sits in the gap with room to spare.
MAX_SINGLE_CHAR_TOKENS = 0.25

# Below this many tokens the ratio is too noisy to judge.
_MIN_TOKENS_FOR_SHAPE = 8

# Content types whose text is legitimately fragmentary.
_FRAGMENT_EXEMPT = {"table", "formula"}


def single_char_token_ratio(text: str) -> float:
    """Fraction of tokens that are one character long."""
    tokens = text.split()
    if not tokens:
        return 0.0
    return sum(1 for token in tokens if len(token) == 1) / len(tokens)

# Scripts a language is expected to be written in.
_EXPECTED_SCRIPT = {
    "hi": "devanagari_chars",
    "pa": "gurmukhi_chars",
    "en": "latin_chars",
}


def _letter_ratio(stats: dict[str, int]) -> float:
    total = stats["total_chars"] - stats["spaces"]
    if total <= 0:
        return 0.0
    letters = stats["latin_chars"] + stats["devanagari_chars"] + stats["gurmukhi_chars"]
    return letters / total


def validate_chunk(chunk: Chunk, seen_hashes: set[str]) -> list[str]:
    """Return the list of issues with a chunk; empty means it passes."""
    issues: list[str] = []
    text = chunk.text.strip()

    if not text:
        return ["empty"]

    stats = text_stats(text)

    if chunk.token_estimate < MIN_TOKENS:
        issues.append("too_short")

    if chunk.token_estimate > HARD_MAX_TOKENS:
        issues.append("too_long")

    # Legacy text that the converter could not repair. It would
    # embed as meaningless Latin and match nothing a student asks.
    if chunk.script == "legacy_devanagari":
        issues.append("unconverted_legacy")

    expected = _EXPECTED_SCRIPT.get(chunk.language)
    if expected and stats[expected] == 0 and stats["total_chars"] > 30:
        issues.append("script_language_mismatch")

    if _letter_ratio(stats) < MIN_LETTER_RATIO and chunk.content_type not in _FRAGMENT_EXEMPT:
        issues.append("low_letter_ratio")

    if (
        chunk.content_type not in _FRAGMENT_EXEMPT
        and len(text.split()) >= _MIN_TOKENS_FOR_SHAPE
        and single_char_token_ratio(text) > MAX_SINGLE_CHAR_TOKENS
    ):
        issues.append("fragmented_text")

    if _REPEAT_RUN.search(text):
        issues.append("repeated_character_run")

    if chunk.text_hash in seen_hashes:
        issues.append("duplicate")

    return issues


def validate_chunks(chunks: list[Chunk]) -> dict[str, Any]:
    """
    Validate every chunk, marking each valid or not.

    Deduplication keeps the first occurrence. Running headers and
    footers repeat on every page of a textbook, and without this the
    index fills with dozens of copies of the chapter title.
    """
    seen_hashes: set[str] = set()
    issue_counts: dict[str, int] = {}

    for chunk in chunks:
        issues = validate_chunk(chunk, seen_hashes)
        chunk.issues = issues
        chunk.valid = not issues

        if chunk.valid:
            seen_hashes.add(chunk.text_hash)

        for issue in issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1

    accepted = [chunk for chunk in chunks if chunk.valid]
    rejected = [chunk for chunk in chunks if not chunk.valid]

    return {
        "total": len(chunks),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "verdict": _verdict(chunks, issue_counts),
        "issues": dict(sorted(issue_counts.items(), key=lambda kv: kv[1], reverse=True)),
        "rejected_samples": [
            {
                "chunk_id": chunk.chunk_id,
                "page": chunk.page,
                "issues": chunk.issues,
                "preview": chunk.text[:120],
            }
            for chunk in rejected[:15]
        ],
    }


# A document is called broken rather than merely poor once this much
# of it fails the same structural check.
_BROKEN_SHARE = 0.4


def _verdict(chunks: list[Chunk], issue_counts: dict[str, int]) -> dict[str, Any]:
    """
    A document-level read on whether this PDF was usable at all.

    Per-chunk rejection is quiet by design, but a PDF whose font has
    no character map fails *every* chunk the same way -- and the
    caller needs to be told the file is unusable, not handed a
    library that silently contains nothing.
    """
    total = len(chunks)
    if not total:
        return {
            "usable": False,
            "reason": "no_text",
            "message": (
                "No text could be extracted. If this is a scanned book it "
                "needs OCR, which is not installed."
            ),
        }

    fragmented = issue_counts.get("fragmented_text", 0) / total
    legacy = issue_counts.get("unconverted_legacy", 0) / total

    if fragmented >= _BROKEN_SHARE:
        return {
            "usable": False,
            "reason": "unreadable_text_layer",
            "share": round(fragmented, 3),
            "message": (
                f"{fragmented:.0%} of this PDF extracted as single characters "
                f"rather than words. Its embedded font has no usable "
                f"character map, so the text layer cannot be read. The file "
                f"would need OCR, or a copy with a proper text layer."
            ),
        }

    if legacy >= _BROKEN_SHARE:
        return {
            "usable": False,
            "reason": "unconverted_legacy",
            "share": round(legacy, 3),
            "message": (
                f"{legacy:.0%} of this PDF is in a legacy font the converter "
                f"could not map. Run `python -m ingestion.cli coverage "
                f"<file.pdf>` to see which characters are missing."
            ),
        }

    return {"usable": True, "reason": "ok", "message": ""}
