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
# A line that has ended its sentence ended its paragraph too if it stops this far
# short of the page's measure. Length is only consulted once a sentence has
# ended -- see _reflow for why it cannot be the first test.
_SHORT_LINE_RATIO = 0.78
# The measure used to be the page's longest line. On a two-column page one
# full-width line -- a definition set across both columns, a caption -- sets a bar
# the body text never reaches: on p.81 of the Class 6 book the widest line is 69,
# the body 45-52, and the old threshold of 54 declared 32 of 41 lines to be the
# end of a paragraph. So the measure now comes from lines that certainly wrapped
# -- the ones followed by a lowercase continuation -- whose median is the column
# width, however many other widths share the page. A page with too few of them
# falls back to a high percentile of everything.
_MIN_WRAPS_FOR_MEASURE = 3
_MEASURE_PERCENTILE = 0.80
# Lines shorter than this say nothing about the column width.
_MIN_MEASURED_CHARS = 20

# "10.8 : Frictional force" is the caption of Figure 10.8, not a section. All 153
# lines of this shape in the Class 6 book are captions. Treated as headings they
# opened a new section wherever the figure happened to sit. Treated as text they
# are no better: extraction places them out of reading order, so they land in
# the middle of a definition -- "... due to gravitational force. 10.5 : Falling
# down of a ball and a mango 10.3 : Lifting a weight" -- and when they were first
# let through they filled 119 of 228 chunks. So a caption, with the lowercase
# tail it wrapped onto, is dropped like a page number.
_FIGURE_CAPTION = re.compile(r"^\d+\.\d+\s*:\s*\S")
# The start of a list item, an exercise option or a bullet: "3. ", "(a) ", "b) ",
# "(iv) ", "• ". Each opens its own paragraph, because the exercise filter in
# rag.quality judges items one paragraph at a time. The book's round bullet
# extracts as a lone "l", which no English sentence starts with.
_ITEM_START = re.compile(
    r"^(?:\d{1,2}\s*[.)]\s|\(\s*[a-z]{1,2}\s*\)|[a-z]\)\s|\(\s*[ivx]{1,4}\s*\)"
    r"|[•●▪◦·]\s|l\s+(?=[A-Z]))"
)
# A line that ends its sentence. The book spaces its question marks ("carrom ?"),
# and a closing quote or bracket may follow.
_ENDS_SENTENCE = re.compile(r"[.!?:;][\"')\]]*$")
# A next line starting like this continues the sentence rather than beginning one.
_CONTINUATION = re.compile(r"^[a-z,;)\]]")
# No heading ends on one of these, and no sentence breaks off after one:
# "Characteristics of", "Determine the directions in the class or".
_DANGLING_WORDS = frozenset(
    "a an and as at by for from in into is are of on or than that the their "
    "its his her him to which with".split()
)


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
    # A heading starts a line of its own; one that starts lowercase is the middle
    # of a sentence ("the Indian scientist Sir C. V. Raman").
    if stripped[:1].islower():
        return False
    if _FIGURE_CAPTION.match(stripped):
        return False
    words = stripped.split()
    if words[-1].lower() in _DANGLING_WORDS:
        return False
    if _NUMBERED_HEADING.match(stripped):
        return True
    if len(words) > 12:
        return False
    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return False
    if all(c.isupper() for c in letters):
        return True
    capitalised = sum(1 for w in words if w[:1].isupper())
    return capitalised >= max(2, int(len(words) * 0.7))


def _measure(lines: Sequence[str]) -> float:
    """The page's column width, taken from the lines that certainly wrapped."""
    wraps = sorted(
        len(line)
        for line, nxt in zip(lines, lines[1:])
        if len(line) >= _MIN_MEASURED_CHARS
        and _CONTINUATION.match(nxt)
        and not _ITEM_START.match(nxt)
    )
    if len(wraps) >= _MIN_WRAPS_FOR_MEASURE:
        return float(wraps[len(wraps) // 2])
    lengths = sorted(len(line) for line in lines if len(line) >= _MIN_MEASURED_CHARS)
    if not lengths:
        lengths = sorted(len(line) for line in lines if line)
    if not lengths:
        return 0.0                       # an image-only page: nothing to measure
    return float(lengths[min(len(lengths) - 1, int(len(lengths) * _MEASURE_PERCENTILE))])


def _opens_body(text: str, long_enough: float) -> bool:
    """What a heading has to be followed by: prose or a list of steps.

    A table's header row -- "Substance Freezing point Boiling point", "Points
    Solids Liquids Gases" -- is as Title-case as any heading, and before this
    became the breadcrumb of whatever section followed the table. What comes
    after it is a column of cells, which neither ends a sentence nor runs long.
    """
    return bool(
        _ENDS_SENTENCE.search(text) or len(text) >= long_enough or _ITEM_START.match(text)
    )


# A paragraph at least this long is body text whether or not extraction kept its
# full stop.
_BODY_PARAGRAPH_CHARS = 80


def is_section_heading(paragraphs: Sequence[str], index: int) -> bool:
    """`paragraphs[index]` opens a section: heading-shaped, and followed by body.

    The chunker's test, on reflowed paragraphs. Context-free looks_like_heading
    is not enough there: a table header or a run of diagram labels passes it,
    and the one that does becomes the label of every chunk until the next real
    heading. A heading followed by another heading qualifies if that one does --
    a chapter title directly above its first section.
    """
    for i in range(index, len(paragraphs)):
        if not looks_like_heading(paragraphs[i]):
            return i > index and _opens_body(paragraphs[i], _BODY_PARAGRAPH_CHARS)
        if i + 1 >= len(paragraphs):
            # Last on its page: the body is on the next one.
            return True
    return False


def _reflow(text: str) -> str:
    """Rejoin the hard line breaks a PDF puts at the end of every visual line.

    Extracted text breaks where the column broke, so one paragraph arrives as a
    dozen short lines -- with no blank line between paragraphs, so there is no
    separator to split on. Joining everything instead produces a single
    page-long blob in which headings vanish into the prose.

    Each line is judged against the one after it, strongest evidence first:

      1. The next line starts lowercase: a continuation, whatever the length.
         "The force applied by means of a machine" / "is called mechanical
         force." is one sentence, and was stored as two paragraphs.
      2. The next line opens a heading, a caption or a list item: a break --
         unless this line trails off on "of", "and" or a comma.
      3. This line does not end a sentence: a wrap -- if it filled the column.
         A short line that stops without punctuation is a label, not a wrap:
         joined, "Candle", "Plastic", "Iron" off a diagram become "Candle
         Plastic Iron", which reads as a heading and labels the next section.
      4. It does end one: a paragraph ends only if the line also stops short of
         the page's measure; a sentence that happens to end at the margin is
         usually followed by more of the same paragraph.

    A list item or a figure caption is stricter than prose: once its sentence
    has ended, it has ended. Joined by length instead, "(c) Jupiter is the
    biggest planet." swallowed the lesson paragraph after it, and the exercise
    filter -- which condemns any paragraph opening on an option marker -- took
    "We should study phenomena like meteor falls, eclipses, etc." with it.

    Line length used to be the first test and the only one. On a two-column
    book that put a paragraph break in 2,365 places mid-sentence and left 65 of
    103 definitions split in two.

    A heading must still survive as its own block -- it is both the boundary
    between topics and the label a chunk carries into its embedding -- but a
    line is only a heading if the next line does not continue it.
    """
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    lines = [line.strip() for line in text.splitlines()]
    if not any(lines):
        return ""
    threshold = _measure(lines) * _SHORT_LINE_RATIO

    def after(i: int) -> str:
        return lines[i + 1] if i + 1 < len(lines) else ""

    def continues(line: str) -> bool:
        return bool(line) and bool(_CONTINUATION.match(line)) and not _ITEM_START.match(line)

    heading_memo: dict = {}

    def heading_at(i: int) -> bool:
        if i in heading_memo:
            return heading_memo[i]
        heading_memo[i] = False          # a run of heading-shaped lines ends somewhere
        line, nxt = lines[i], after(i)
        if not looks_like_heading(line) or continues(nxt):
            return False
        # "3. Forest fires" followed by "4. Increased risk ..." is a list.
        if _ITEM_START.match(line) and _ITEM_START.match(nxt):
            return False
        result = not nxt or _opens_body(nxt, threshold) or heading_at(i + 1)
        heading_memo[i] = result
        return result

    def caption_tail(line: str) -> bool:
        # A caption wraps onto a short noun phrase: "gases in the air". What a
        # caption does NOT own is the body text extraction happened to put after
        # it, which also starts lowercase because its sentence began elsewhere --
        # "less force is required to lift the paperweight. Such a" on p.97. Joined
        # to the caption, that went down with it, and took "Such a lever is called
        # a lever of the first order." out of the corpus.
        return len(line) < threshold and not re.search(r"[.!?]", line)

    def trails_off(line: str) -> bool:
        words = line.split()
        return line.endswith(",") or (bool(words) and words[-1].lower() in _DANGLING_WORDS)

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
            caption = bool(_FIGURE_CAPTION.match(line))
            item = bool(_ITEM_START.match(line))
        current.append(line)

        nxt = after(i)
        if not nxt:
            join = False
        elif continues(nxt):
            join = not caption or caption_tail(nxt)
        elif _ITEM_START.match(nxt) or _FIGURE_CAPTION.match(nxt) or heading_at(i + 1):
            # Never into a caption: whatever it absorbs is dropped with it.
            join = trails_off(line) and not caption
        elif caption:
            # A caption is only ever continued by its own lowercase tail.
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
