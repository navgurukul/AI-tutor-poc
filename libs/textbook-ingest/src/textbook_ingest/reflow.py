"""S5 -- rejoin the hard line breaks a PDF puts at the end of every visual line.

This stage is carried over almost unchanged, because it is the one part of the
old pipeline that generalised. Measured across all eight books the inferred
column width lands between 25 and 74 characters and the median chunk stays
between 515 and 556 against a 700 target, with no publisher-specific tuning.

Extracted text breaks where the column broke, so one paragraph arrives as a
dozen short lines with no blank line between paragraphs. Joining everything
produces a page-long blob in which headings vanish; splitting on length alone
put a paragraph break in 2,365 places mid-sentence on the MSCERT book and left
65 of 103 definitions in two halves.

Each line is judged against the one after it, strongest evidence first:

  1. the next line starts lowercase -> a continuation, whatever the length;
  2. the next line opens a heading, caption or list item -> a break, unless this
     line trails off on "of", "and" or a comma;
  3. this line does not end a sentence -> a wrap, if it filled the column;
  4. it does end one -> a paragraph ends only if the line also stops short of
     the measure, since a sentence ending at the margin usually continues.

The measure is taken from lines that certainly wrapped -- the ones followed by a
lowercase continuation -- because on a two-column page one full-width line sets
a bar the body never reaches.
"""

import re
from typing import Dict, List, Optional, Sequence

from .structure import (
    is_caption,
    is_item_start,
    looks_like_heading,
    opens_body,
)
from .types import BookProfile

_SHORT_LINE_RATIO = 0.78
_MIN_WRAPS_FOR_MEASURE = 3
_MEASURE_PERCENTILE = 0.80
_MIN_MEASURED_CHARS = 20

_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*([a-z])")
_EXCESS_BLANKS = re.compile(r"\n{3,}")
_TRAILING_SPACE = re.compile(r"[ \t]+\n")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_CONTINUATION = re.compile(r"^[a-z,;)\]]")
_ENDS_SENTENCE = re.compile(r"[.!?:;][\"')\]]*$")
_DANGLING = frozenset(
    "a an and as at by for from in into is are of on or than that the their its "
    "his her him to which with".split()
)


def measure(lines: Sequence[str], profile: Optional[BookProfile] = None) -> float:
    """The page's column width, taken from the lines that certainly wrapped."""
    wraps = sorted(
        len(line)
        for line, nxt in zip(lines, lines[1:])
        if len(line) >= _MIN_MEASURED_CHARS
        and _CONTINUATION.match(nxt)
        and not is_item_start(nxt, profile)
    )
    if len(wraps) >= _MIN_WRAPS_FOR_MEASURE:
        return float(wraps[len(wraps) // 2])
    lengths = sorted(len(line) for line in lines if len(line) >= _MIN_MEASURED_CHARS)
    if not lengths:
        lengths = sorted(len(line) for line in lines if line)
    if not lengths:
        return 0.0
    return float(lengths[min(len(lengths) - 1, int(len(lengths) * _MEASURE_PERCENTILE))])


def reflow_page(text: str, profile: Optional[BookProfile] = None) -> str:
    """Turn one stripped page into blank-line-separated paragraphs."""
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    lines = [line.strip() for line in text.splitlines()]
    if not any(lines):
        return ""
    threshold = measure(lines, profile) * _SHORT_LINE_RATIO

    def after(i: int) -> str:
        return lines[i + 1] if i + 1 < len(lines) else ""

    def continues(line: str) -> bool:
        return bool(line) and bool(_CONTINUATION.match(line)) and not is_item_start(line, profile)

    heading_memo: Dict[int, bool] = {}

    def heading_at(i: int) -> bool:
        if i in heading_memo:
            return heading_memo[i]
        heading_memo[i] = False          # a run of heading-shaped lines ends somewhere
        line, nxt = lines[i], after(i)
        if not looks_like_heading(line, profile) or continues(nxt):
            return False
        # "3. Forest fires" followed by "4. Increased risk..." is a list.
        if is_item_start(line, profile) and is_item_start(nxt, profile):
            return False
        result = not nxt or opens_body(nxt, threshold) or heading_at(i + 1)
        heading_memo[i] = result
        return result

    def caption_tail(line: str) -> bool:
        # A caption wraps onto a short noun phrase. What it does NOT own is the
        # body text extraction happened to put after it, which also starts
        # lowercase because its sentence began elsewhere.
        return len(line) < threshold and not re.search(r"[.!?]", line)

    def trails_off(line: str) -> bool:
        words = line.split()
        return line.endswith(",") or (bool(words) and words[-1].lower() in _DANGLING)

    paragraphs: List[str] = []
    current: List[str] = []
    caption = False
    item = False

    def close() -> None:
        if current:
            joined = _MULTI_SPACE.sub(" ", " ".join(current)).strip()
            if joined and not caption:
                paragraphs.append(joined)
            current.clear()

    for i, line in enumerate(lines):
        if not line:
            close()
            continue
        if not current:
            if heading_at(i):
                paragraphs.append(line)
                continue
            caption = is_caption(line, profile)
            item = is_item_start(line, profile)
        current.append(line)

        nxt = after(i)
        if not nxt:
            join = False
        elif continues(nxt):
            join = not caption or caption_tail(nxt)
        elif is_item_start(nxt, profile) or is_caption(nxt, profile) or heading_at(i + 1):
            # Never join into a caption: whatever it absorbs is dropped with it.
            join = trails_off(line) and not caption
        elif caption:
            join = False
        elif not _ENDS_SENTENCE.search(line):
            join = len(line) >= threshold or trails_off(line)
        elif item:
            join = False
        else:
            join = len(line) >= threshold
        if not join:
            close()
    close()
    return "\n\n".join(paragraphs)


def reflow_pages(pages: Sequence[str], profile: Optional[BookProfile] = None) -> List[str]:
    out = []
    for page in pages:
        text = reflow_page(page, profile)
        out.append(_EXCESS_BLANKS.sub("\n\n", _TRAILING_SPACE.sub("\n", text)).strip())
    return out
