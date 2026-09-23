"""Stage 6b -- running heads, folios and other page furniture.

The ported pipeline had no equivalent of this and needs one. `pdf_text`, the
line-statistical module this package replaces, removed furniture statistically
and would otherwise have been strictly better at one thing while being worse at
everything else.

Furniture is worse here than it was there, because the classifier promotes it.
A running head is short, set larger or bolder than the body, and carries no
terminal punctuation -- which is the exact signature `classify` uses for a
heading. So the book's own title becomes a *section*, and `chunk` then files
every passage beneath it under that section, and `embedding_text` puts it in
front of the text as the breadcrumb.

Measured on the live Class X Geography library (2026-09-20), where the old
pipeline's line-level removal had already missed it:

    41 of 369 chunks (11%) were filed under "समकालीन भारत-2", the book title
    88 more (24%) under a fragment or an MCQ option
    => the breadcrumb carried no topic signal for 35% of the library

The breadcrumb exists so that a paragraph reading "It evaporates and rises"
still carries "Water cycle" into vector space. Filled with the book's title,
which is identical on every page, it carries nothing and costs tokens.

Detection is statistical, not a pattern list, so it adapts to whatever book is
loaded rather than to NCERT specifically.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .model import Block, Document, Page

# How far into the page an edge band reaches, as a share of page height.
# A running head sits in the top band, a folio in the bottom one; body text
# that happens to be short does not.
EDGE_BAND = 0.14

# A stem must appear at the edge on at least this many pages to be furniture.
# Three is enough to be sure a varying trailing number is tracking the page
# rather than being part of the title, and low enough to catch a running head
# that spans only one chapter of a multi-chapter file.
MIN_PAGES = 3

# ...and on at least this share of them, so that a book whose first chapter
# repeats a phrase three times does not lose it.
MIN_PAGE_SHARE = 0.12

# Below this many pages the statistics mean nothing -- in a 3-page handout
# every line looks repeated.
MIN_PAGES_FOR_DETECTION = 6

# A running head carries the page number with it -- "SCIENCE 12", "समकालीन
# भारत-2 48" -- so the exact string differs on every page and exact-match
# counting never sees a repeat. This strips it back to a stem.
_EDGE_PAGE_NUMBER = re.compile(r"[\s|\-–—_.]*[\d०-९]{1,4}[\s|\-–—_.]*$")
_NON_ALNUM = re.compile(r"[^0-9A-Za-zऀ-ॿ]+")

# A line that is only a page number, however decorated: "- 87 -", "|87|",
# "viii". Roman numerals are included because front matter uses them and the
# old pipeline missed them ("viii" was sitting inside a chunk's text).
_PAGE_NUMBER_ONLY = re.compile(
    r"^[\s|\-–—_.()\[\]]*(?:[\d०-९]{1,4}|[ivxlcdm]{1,7}|[IVXLCDM]{1,7})[\s|\-–—_.()\[\]]*$"
)

# NCERT prints this on every page of the reprint editions.
_REPRINT_WATERMARK = re.compile(r"reprint\s*\d{4}\s*[-–]\s*\d{2,4}", re.IGNORECASE)

# A running head is a label, not a sentence. Body prose that happens to end in
# a varying number -- "...as shown in equation 12." at the foot of a page --
# reaches the same code path, and without these two guards the stem rule eats
# it.
_ENDS_A_SENTENCE = re.compile(r"[.!?।॥]\s*$")
MAX_RUNNING_HEAD_CHARS = 70


def stem_of(text: str) -> str:
    """A page-number-free, spacing-free key for an edge line.

    Every non-alphanumeric character goes, not merely runs of whitespace:
    textbook running heads are frequently letter-spaced for effect, so
    "MA TTER  IN O UR  S URROUNDING S" and "MATTER IN OUR SURROUNDINGS" are
    the same head and must produce the same key.
    """
    return _NON_ALNUM.sub("", _EDGE_PAGE_NUMBER.sub("", text.strip())).lower()


def _is_edge(block: Block, page: Page) -> bool:
    if page.height <= 0:
        return False
    band = page.height * EDGE_BAND
    return block.bbox[1] <= band or block.bbox[3] >= page.height - band


def _could_be_furniture(text: str) -> bool:
    text = text.strip()
    if not text or len(text) > MAX_RUNNING_HEAD_CHARS:
        return False
    return not _ENDS_A_SENTENCE.search(text)


def find_repeated_stems(document: Document) -> Dict[str, int]:
    """Stems that appear at a page edge on several pages, with their counts."""
    pages = len(document.pages)
    if pages < MIN_PAGES_FOR_DETECTION:
        return {}

    seen: Dict[str, set] = {}
    for page in document.pages:
        for block in page.text_blocks:
            text = block.normalized_text or block.text
            if not _is_edge(block, page) or not _could_be_furniture(text):
                continue
            stem = stem_of(text)
            if len(stem) < 3:
                continue
            seen.setdefault(stem, set()).add(page.number)

    threshold = max(MIN_PAGES, int(MIN_PAGE_SHARE * pages))
    return {
        stem: len(page_numbers)
        for stem, page_numbers in seen.items()
        if len(page_numbers) >= threshold
    }


def mark_furniture(document: Document) -> Dict[str, int]:
    """Retype every furniture block as `furniture`, which chunking skips.

    Retyped rather than deleted: the block stays in the document so an ingest
    report can show what was removed and why. A pipeline that silently drops
    text is one nobody can debug when it drops the wrong text.
    """
    repeated = find_repeated_stems(document)
    counts: Dict[str, int] = {}

    def mark(block: Block, reason: str) -> None:
        block.content_type = "furniture"
        block.classification_evidence = {
            **block.classification_evidence, "furniture_reason": reason
        }
        counts[reason] = counts.get(reason, 0) + 1

    for page in document.pages:
        for block in page.text_blocks:
            text = (block.normalized_text or block.text).strip()
            if not text:
                continue

            if _PAGE_NUMBER_ONLY.match(text):
                mark(block, "page_number")
                continue

            if _REPRINT_WATERMARK.search(text):
                mark(block, "watermark")
                continue

            if (
                _is_edge(block, page)
                and _could_be_furniture(text)
                and stem_of(text) in repeated
            ):
                mark(block, "running_head")

    if counts:
        document.summary["furniture"] = {
            "removed": sum(counts.values()),
            "by_reason": counts,
            "stems": sorted(repeated, key=lambda s: repeated[s], reverse=True)[:10],
        }
    return counts


def strip_inline_furniture(document: Document) -> int:
    """Remove a folio or watermark that shares a block with real text.

    A page number is its own block on most pages and a line inside one on the
    rest, depending on how the generator grouped things. The block-level pass
    above cannot touch the second case without discarding the paragraph it is
    sitting in, so it is handled line by line here.
    """
    removed = 0
    for page in document.pages:
        for block in page.text_blocks:
            if block.content_type == "furniture":
                continue
            lines = (block.normalized_text or "").split("\n")
            if len(lines) < 2:
                continue
            kept: List[str] = []
            for line in lines:
                stripped = line.strip()
                if _PAGE_NUMBER_ONLY.match(stripped) or _REPRINT_WATERMARK.search(stripped):
                    removed += 1
                    continue
                kept.append(line)
            if len(kept) != len(lines):
                block.normalized_text = "\n".join(kept).strip()
    return removed


def run(document: Document) -> Tuple[Dict[str, int], int]:
    """Mark furniture blocks, then strip furniture lines from the rest."""
    return mark_furniture(document), strip_inline_furniture(document)
