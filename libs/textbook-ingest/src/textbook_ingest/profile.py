"""S3 -- learn this book's furniture instead of hard-coding one publisher's.

The old detector counted identical lines and asked for one on 45% of pages. It
caught nothing on the MSCERT book (which has no running header) and exactly one
line per NCERT book (the bare "2020-21" edition footer). It missed every actual
running header, for two reasons, and both are fixed here.

FIRST: THE PAGE NUMBER IS PART OF THE HEADER.

    SCIENCE58 / THE FUNDAMENTAL UNIT OF LIFE 59 / SCIENCE60 / ...

Every instance is a different string, so counting literals counts each once.
Normalising the number out first collapses them to two templates. Measured on
one Class 9 chapter: literal counting catches 1 line, template counting catches
both the verso and the recto header.

SECOND: THE THRESHOLD CANNOT BE BOOK-WIDE.

A running header that carries the chapter title changes every chapter. Over 8
merged Class 9 chapters, "SCIENCE" appears on 51 of 113 pages and clears 45%,
but "MOTION" appears on 8 -- 7% of the book, and unmissably a header within its
own chapter. So density is measured over the span a template actually occupies,
not over the book. "MOTION" is on 8 of the 14 pages between its first and last
appearance, which is 57%, and it is caught.

The same frequency reasoning gives the rest of the profile. The NCERT label
vocabulary -- QUESTIONS, Exercises, What you have learnt, Activity 1..7 -- was
originally found by counting recurring short lines, so that is how the library
finds it too, rather than by growing a regex that will be wrong for the next
publisher.
"""

import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .types import BookProfile

# How many lines at each end of a page can be furniture: a header, a footer and
# a chapter strap line, without reaching into the body.
_EDGE_LINES = 3
# A running header is short. Anything longer is a sentence that happens to sit
# at the top of a page.
_MAX_FURNITURE_CHARS = 90
# Share of its own span a template must occupy.
_SPAN_DENSITY = 0.40
# ...on at least this many pages, so two adjacent coincidences are not furniture.
_MIN_FURNITURE_PAGES = 3
# ...spanning at least this much, so a template confined to two pages is not
# promoted on a density of 1.0.
_MIN_FURNITURE_SPAN = 5

# A leading or trailing page number, which is what makes every header unique.
_EDGE_NUMBER = re.compile(r"^\s*\d{1,4}\s*|\s*\d{1,4}\s*$")

# Section labels: short, recurring, standing alone.
_MAX_LABEL_CHARS = 46
_MIN_LABEL_HITS = 3

# Caption forms. NCERT writes "Fig. 8.3: ...", MSCERT writes "10.8 : ...".
_CAPTION_PREFIXED = re.compile(
    r"^(?:fig|figure|table|chart|photo|map|graph)s?\.?\s*\d+(?:\.\d+)*", re.IGNORECASE
)
_CAPTION_NUMERIC = re.compile(r"^\d+\.\d+\s*:\s*\S")
_MIN_CAPTION_HITS = 5

# Bullets. The MSCERT round bullet extracts as a lowercase L; NCERT Class 10
# yields the glyph NAME "/square6". Neither is a character any rule would guess.
_BULLET_CANDIDATE = re.compile(r"^(\S{1,9})\s+(?=[A-Za-z(])")
_KNOWN_BULLETS = set("•●▪◦·‣⁃-*")
_MIN_BULLET_HITS = 6


def template(line: str) -> str:
    """The line with its page number taken off both ends and spaces squeezed.

    "SCIENCE58" and "SCIENCE60" both become "SCIENCE"; "THE FUNDAMENTAL UNIT OF
    LIFE 59" becomes "THE FUNDAMENTAL UNIT OF LIFE". Applied twice because a
    header can carry a number at each end.
    """
    stripped = _EDGE_NUMBER.sub("", line, count=1)
    stripped = _EDGE_NUMBER.sub("", stripped, count=1)
    return " ".join(stripped.split())


def _page_lines(page: str) -> List[str]:
    return [line.strip() for line in page.splitlines() if line.strip()]


def _edge_templates(pages: Sequence[str]) -> Dict[Tuple[str, str], List[int]]:
    """Where each (edge, template) pair appears, by page index."""
    seen: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for index, page in enumerate(pages):
        lines = _page_lines(page)
        if not lines:
            continue
        for edge, group in (("top", lines[:_EDGE_LINES]), ("bottom", lines[-_EDGE_LINES:])):
            for line in set(group):
                if 2 < len(line) <= _MAX_FURNITURE_CHARS:
                    key = (edge, template(line))
                    if len(key[1]) > 2 and index not in seen[key]:
                        seen[key].append(index)
    return seen


def detect_furniture(pages: Sequence[str]) -> Set[str]:
    """Templates that behave like a running header or footer.

    Density is measured over the span between a template's first and last
    appearance, not over the book, so a header that only runs for one chapter is
    still caught. See the module docstring for why that distinction is
    load-bearing.
    """
    furniture: Set[str] = set()
    for (_edge, tpl), indices in _edge_templates(pages).items():
        if len(indices) < _MIN_FURNITURE_PAGES:
            continue
        span = indices[-1] - indices[0] + 1
        if span < _MIN_FURNITURE_SPAN:
            continue
        if len(indices) / span >= _SPAN_DENSITY:
            furniture.add(tpl)
    return furniture


def detect_labels(pages: Sequence[str], furniture: Set[str]) -> Set[str]:
    """Short lines this book repeats: its own box and section vocabulary.

    Capped at a short length so a recurring *sentence* is never learned as a
    label -- dropping a one-line label costs nothing, dropping a sentence is the
    mistake no later stage can undo.
    """
    counts: Counter = Counter()
    for page in pages:
        for line in _page_lines(page):
            if len(line) <= _MAX_LABEL_CHARS and line[:1].isalpha():
                flat = " ".join(line.split())
                if flat and template(flat) not in furniture:
                    counts[flat] += 1
    return {line for line, hits in counts.items() if hits >= _MIN_LABEL_HITS}


def detect_caption_style(pages: Sequence[str]) -> str:
    """Which caption form this book uses: "prefixed", "numeric" or "none"."""
    prefixed = numeric = 0
    for page in pages:
        for line in _page_lines(page):
            if _CAPTION_PREFIXED.match(line):
                prefixed += 1
            elif _CAPTION_NUMERIC.match(line):
                numeric += 1
    if max(prefixed, numeric) < _MIN_CAPTION_HITS:
        return "none"
    return "prefixed" if prefixed >= numeric else "numeric"


def detect_bullets(pages: Sequence[str]) -> Set[str]:
    """The tokens this book starts a list item with.

    Counted rather than assumed, because the token is often not a bullet
    character at all: a glyph name that leaked through extraction ("/square6"),
    or a letter that happens to be the font's bullet slot ("l").
    """
    counts: Counter = Counter()
    for page in pages:
        for line in _page_lines(page):
            match = _BULLET_CANDIDATE.match(line)
            if not match:
                continue
            token = match.group(1)
            if token in _KNOWN_BULLETS or token.startswith("/") or token in {"l", "L"}:
                counts[token] += 1
    return {token for token, hits in counts.items() if hits >= _MIN_BULLET_HITS}


def build_profile(
    pages: Sequence[str],
    vocabulary: Optional[Dict[str, int]] = None,
    space_substitute: Optional[str] = None,
) -> BookProfile:
    """One pass over the book that yields everything publisher-specific."""
    furniture = detect_furniture(pages)
    return BookProfile(
        furniture=furniture,
        labels=detect_labels(pages, furniture),
        caption_style=detect_caption_style(pages),
        bullets=detect_bullets(pages),
        space_substitute=space_substitute,
        vocabulary=dict(vocabulary or {}),
    )
