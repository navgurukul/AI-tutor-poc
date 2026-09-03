"""Turn a school textbook PDF into clean, chunkable text.

Extraction is the easy half. The half that decides retrieval quality is what
comes after it: a textbook page carries a running header, a page number, a
reprint watermark and hyphenated line breaks, and every one of those becomes
noise inside an embedding if it survives into a chunk. A chunk that reads
"CHAPTER 6 TISSUES 87 Reprint 2025-26 plant tis- sues are of two types" embeds
badly and reads badly when it is pasted into the prompt.

Nothing here is NCERT-specific beyond one watermark pattern; the header and
footer removal is statistical, so it adapts to whatever book is fed in.
"""

import logging
import re
import unicodedata
from collections import Counter
from typing import List, Sequence, Tuple

logger = logging.getLogger(__name__)

# A line has to appear on at least this share of pages to count as furniture.
# Too low and a genuinely repeated sentence gets deleted; too high and the
# header survives on books whose first pages differ.
_REPEAT_THRESHOLD = 0.45
# Below this many pages the statistics are meaningless -- a 3-page handout
# would have every line looking "repeated".
_MIN_PAGES_FOR_REPEAT_DETECTION = 6

# Lines that are only a page number, optionally decorated ("- 87 -", "|87|").
_PAGE_NUMBER = re.compile(r"^[\s|\-–—_.]*\d{1,4}[\s|\-–—_.]*$")
# NCERT prints this on every page of the reprint editions.
_REPRINT_WATERMARK = re.compile(r"reprint\s*\d{4}\s*[-–]\s*\d{2,4}", re.IGNORECASE)
# A word broken across a line break: "tis-\nsues" -> "tissues". Only joined when
# the next line starts lowercase, so "self-\nEvident" and real hyphenated
# compounds at a line end are left alone.
_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*([a-z])")
# Three or more blank lines collapse to a paragraph break.
_EXCESS_BLANKS = re.compile(r"\n{3,}")
_TRAILING_SPACE = re.compile(r"[ \t]+\n")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
# A line with almost no letters is extraction debris from a diagram or a rule.
_MOSTLY_SYMBOLS = re.compile(r"^[^A-Za-z0-9]{3,}$")

# Ligatures and typographic characters that pypdf hands back verbatim. NFKC
# handles the ligatures, but not the quotes and dashes, and a chunk containing
# a curly apostrophe tokenises differently from one containing a straight one.
_PUNCTUATION_MAP = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
    "​": "", "﻿": "", "­": "",
}


class PdfExtractionError(Exception):
    """Raised when a file cannot be read as a PDF at all."""


def _normalise_characters(text: str) -> str:
    """Fold the PDF's typographic characters down to plain ASCII-ish text.

    NFKC turns the "fi"/"fl" ligatures that textbooks are full of back into
    real letters, which matters because "ﬂower" and "flower" are different
    tokens to the embedding model and only one of them is a word.
    """
    for source, target in _PUNCTUATION_MAP.items():
        text = text.replace(source, target)
    return unicodedata.normalize("NFKC", text)


def _page_lines(page_text: str) -> List[str]:
    return [line.strip() for line in page_text.splitlines()]


def _find_repeated_lines(pages: Sequence[str]) -> set:
    """Identify running headers and footers by how often they repeat.

    Only the first and last few lines of each page are considered: a sentence
    that legitimately recurs in body text ("Activity 6.1") should not be
    stripped, but the same string sitting at the top of forty pages is a header.
    """
    if len(pages) < _MIN_PAGES_FOR_REPEAT_DETECTION:
        return set()

    counts: Counter = Counter()
    for page in pages:
        lines = [line for line in _page_lines(page) if line]
        # Three from each end is enough for a header, a footer, and a chapter
        # strap line, without reaching into the body.
        edges = lines[:3] + lines[-3:]
        for line in set(edges):
            if len(line) > 2:
                counts[line] += 1

    cutoff = max(2, int(len(pages) * _REPEAT_THRESHOLD))
    repeated = {line for line, count in counts.items() if count >= cutoff}
    if repeated:
        logger.info("Dropping %d repeated header/footer line(s)", len(repeated))
    return repeated


def _clean_page(page_text: str, repeated: set) -> str:
    kept: List[str] = []
    for line in _page_lines(page_text):
        if not line:
            kept.append("")
            continue
        if line in repeated:
            continue
        if _PAGE_NUMBER.match(line):
            continue
        if _REPRINT_WATERMARK.search(line):
            continue
        if _MOSTLY_SYMBOLS.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


# "6.2 Plant Tissues" / "1.10.3 Something" -- numbered sections are the most
# reliable heading signal in a textbook.
_NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S")
_MAX_HEADING_CHARS = 90
# A heading may end in a question mark -- textbooks are full of them ("What
# are Tissues?", "Why do we fall ill?") -- so only the punctuation that ends
# a *sentence mid-prose* disqualifies a line.
_SENTENCE_END = re.compile(r"[.,;:]$")
# A line this much shorter than the page's full measure ended its paragraph
# rather than wrapping. 0.78 is deliberately generous: a false split costs one
# extra paragraph boundary, a missed one merges two topics into a chunk.
_SHORT_LINE_RATIO = 0.78


def looks_like_heading(line: str) -> bool:
    """True for a section heading rather than body text.

    Used during reflow -- a heading must survive as its own block, because it
    is both the boundary between topics and the label a chunk carries into its
    embedding.
    """
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return False
    if _SENTENCE_END.search(stripped):
        return False
    if _NUMBERED_HEADING.match(stripped):
        return True
    words = stripped.split()
    if len(words) > 12:
        return False
    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return False
    if all(c.isupper() for c in letters):
        return True
    capitalised = sum(1 for w in words if w[:1].isupper())
    return capitalised >= max(2, int(len(words) * 0.7))


def _reflow(text: str) -> str:
    """Rejoin the hard line breaks a PDF puts at the end of every visual line.

    Extracted text breaks where the column broke, so one paragraph arrives as a
    dozen short lines -- and crucially with no blank line between paragraphs,
    so there is no separator to split on. Joining everything instead produces a
    single page-long blob in which headings vanish into the prose.

    So paragraph ends are inferred from line length: a line that stops well
    short of the page measure is the end of a paragraph, not a wrap. Headings
    are recognised first and kept as their own block.
    """
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    lines = text.splitlines()
    measured = [len(l.strip()) for l in lines if l.strip()]
    if not measured:
        return ""
    # The full measure is the widest line; on a normal page most body lines sit
    # close to it, and only paragraph-final lines fall short.
    threshold = max(measured) * _SHORT_LINE_RATIO

    paragraphs: List[str] = []
    current: List[str] = []

    def close() -> None:
        if current:
            joined = _MULTI_SPACE.sub(" ", " ".join(current)).strip()
            if joined:
                paragraphs.append(joined)
            current.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            close()
            continue
        if looks_like_heading(line):
            close()
            paragraphs.append(line)
            continue
        current.append(line)
        if len(line) < threshold:
            close()
    close()
    return "\n\n".join(paragraphs)


def extract_pages(data: bytes) -> List[str]:
    """Raw per-page text, in reading order. Raises PdfExtractionError."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise PdfExtractionError(
            "pypdf is not installed. Run: pip install -r requirements.txt"
        ) from exc

    import io

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # An empty password unlocks the common "no printing" case; a real
            # password is a genuine failure the user has to resolve.
            try:
                reader.decrypt("")
            except Exception as exc:
                raise PdfExtractionError(
                    "This PDF is password-protected. Remove the password and try again."
                ) from exc
        return [(page.extract_text() or "") for page in reader.pages]
    except PdfExtractionError:
        raise
    except Exception as exc:
        raise PdfExtractionError(
            "Could not read this file as a PDF ({}).".format(exc)
        ) from exc


def clean_pages(pages: Sequence[str]) -> List[str]:
    """Normalise, strip furniture and reflow every page.

    Returned list is parallel to the input, so a chunk can still be traced back
    to the page it came from -- which is what lets an answer cite "page 87".
    """
    normalised = [_normalise_characters(p) for p in pages]
    repeated = _find_repeated_lines(normalised)
    cleaned = []
    for page in normalised:
        stripped = _clean_page(page, repeated)
        reflowed = _reflow(stripped)
        cleaned.append(_EXCESS_BLANKS.sub("\n\n", _TRAILING_SPACE.sub("\n", reflowed)).strip())
    return cleaned


def looks_like_scan(cleaned_pages: Sequence[str]) -> bool:
    """True when a PDF is images with no text layer.

    Worth detecting explicitly: ingestion of a scanned book "succeeds" with
    zero usable text, and the failure would otherwise only show up later as a
    tutor that never finds anything.
    """
    if not cleaned_pages:
        return True
    total = sum(len(p) for p in cleaned_pages)
    return total < 200 * len(cleaned_pages) ** 0.5


def extract_and_clean(data: bytes) -> Tuple[List[str], int]:
    """Convenience wrapper: returns (cleaned pages, raw page count)."""
    raw = extract_pages(data)
    return clean_pages(raw), len(raw)
