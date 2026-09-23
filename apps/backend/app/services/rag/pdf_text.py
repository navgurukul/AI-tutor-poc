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
from typing import List, Optional, Sequence, Tuple

from app.services.rag import devanagari, legacy_hindi

logger = logging.getLogger(__name__)

# A line has to appear on at least this share of pages to count as furniture.
# Too low and a genuinely repeated sentence gets deleted; too high and the
# header survives on books whose first pages differ.
_REPEAT_THRESHOLD = 0.45
# Below this many pages the statistics are meaningless -- a 3-page handout
# would have every line looking "repeated".
_MIN_PAGES_FOR_REPEAT_DETECTION = 6

# A running head carries the page number with it -- "SCIENCE 12",
# "MATTER IN OUR SURROUNDINGS 7" -- so the exact string differs on every page
# and exact-match counting never sees a repeat. These strip it back to a stem.
_EDGE_PAGE_NUMBER = re.compile(r"[\s|\-–—_.]*\d{1,4}[\s|\-–—_.]*$")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z\u0900-\u097F]+")
# A stem seen at the page edge on at least this many pages, with a *different*
# trailing page number each time, is furniture. Three is enough to be sure the
# number is tracking the page rather than being part of the title, and low
# enough to catch a running head that only spans one chapter.
_MIN_RUNNING_HEAD_PAGES = 3
# A running head is a label, not a sentence. Body prose that happens to end in
# a varying number -- "A further remark, number 20." at the foot of a page, or
# "...as shown in equation 12." -- reaches exactly the same code path, and
# without these two guards the stem rule eats it.
_ENDS_A_SENTENCE = re.compile(r"[.!?]\s*$")
# Length is measured in characters, not words: these lines are often
# letter-spaced, so "MA TTER  IN O UR  S URROUNDING S 7" counts as nine words
# while being a 34-character strap line.
_MAX_RUNNING_HEAD_CHARS = 60

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
# A line with no letters or digits at all is extraction debris from a diagram
# or a rule. The character class must be Unicode-aware: written as
# [^A-Za-z0-9] it matched every line of a Devanagari book, because Devanagari
# contains no ASCII letters -- which silently discarded 70% of the first Hindi
# textbook put through the pipeline (197,085 characters in, 58,450 out) and
# could not be seen at all while the corpus was English-only.
_MOSTLY_SYMBOLS = re.compile(r"^[^\w]{3,}$", re.UNICODE)

# Ligatures and typographic characters that PDF text comes back with. NFKC
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
    text = unicodedata.normalize("NFKC", text)
    # Font-map damage: doubled matras, and the फ family. Shared with the
    # structural pipeline so the two cannot drift apart.
    return devanagari.repair(text)


# Devanagari font-map repairs now live in `devanagari`; see that module for
# what they are and what each one was measured on.


def _page_lines(page_text: str) -> List[str]:
    return [line.strip() for line in page_text.splitlines()]


def _running_head_stem(line: str) -> str:
    """A page-number-free, spacing-free key for an edge line.

    Removing every non-alphanumeric character rather than merely collapsing
    runs of whitespace is deliberate: textbook running heads are frequently
    letter-spaced for effect, and extraction hands them back with the spacing
    intact -- "MA TTER  IN O UR  S URROUNDING S 7". Only by discarding the
    spaces entirely does that land on the same key as its neighbours.
    """
    return _NON_ALNUM.sub("", _EDGE_PAGE_NUMBER.sub("", line)).lower()


def _find_repeated_lines(pages: Sequence[str]) -> set:
    """Identify running headers and footers, and return the exact lines to drop.

    Only the first and last few lines of each page are considered: a sentence
    that legitimately recurs in body text ("Activity 6.1") should not be
    stripped, but the same string sitting at the top of forty pages is a header.

    Two rules, because running heads come in two shapes.

    A *constant* header is the same string every time and is caught by counting
    exact lines against a share-of-pages threshold.

    A *numbered* running head carries the page number -- "SCIENCE 2",
    "SCIENCE 10" -- so every occurrence is a different string, each appears
    exactly once, and exact counting never fires. Worse, the threshold cannot
    simply be lowered: a per-chapter running head like "TISSUES 71" covers only
    a dozen pages of a 215-page book, well under any safe share. So these are
    matched on their stem instead, and confirmed by the page number *varying*
    across occurrences -- which is what distinguishes a running head from a
    heading that merely happens to start with a number.
    """
    if len(pages) < _MIN_PAGES_FOR_REPEAT_DETECTION:
        return set()

    counts: Counter = Counter()
    # stem -> {trailing number seen: an exact line carrying it}
    stems: dict = {}
    for page in pages:
        lines = [line for line in _page_lines(page) if line]
        # Three from each end is enough for a header, a footer, and a chapter
        # strap line, without reaching into the body.
        edges = lines[:3] + lines[-3:]
        for line in set(edges):
            if len(line) <= 2:
                continue
            counts[line] += 1
            number = _EDGE_PAGE_NUMBER.search(line)
            if not number:
                continue
            # Prose, not furniture: a chapter strap line does not end in a
            # full stop, and is not a whole sentence long.
            if _ENDS_A_SENTENCE.search(line):
                continue
            if len(line) > _MAX_RUNNING_HEAD_CHARS:
                continue
            stem = _running_head_stem(line)
            if len(stem) < 3:
                continue
            stems.setdefault(stem, {}).setdefault(number.group().strip(), set()).add(line)

    cutoff = max(2, int(len(pages) * _REPEAT_THRESHOLD))
    repeated = {line for line, count in counts.items() if count >= cutoff}

    numbered = set()
    for stem, by_number in stems.items():
        if len(by_number) < _MIN_RUNNING_HEAD_PAGES:
            continue  # the number never varied, so it is part of the title
        for lines in by_number.values():
            numbered |= lines
    repeated |= numbered

    if repeated:
        logger.info(
            "Dropping %d header/footer line(s) (%d numbered running heads)",
            len(repeated), len(numbered),
        )
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
# "1.2 : Proportion of land and water" -- in a textbook a colon straight after
# the figure number is a caption, never a section heading. Measured on the
# Class 6 Science book, this single pattern accounted for a large share of the
# spurious hard cuts.
_FIGURE_CAPTION = re.compile(r"^\d+(?:\.\d+)*\s*:")
# Table-of-contents dot leaders: "3. Diversity in Living Things ............"
_DOT_LEADER = re.compile(r"\.{4,}")
# Curriculum codes in the front matter: "06.72.01 Identifies materials and..."
_OUTCOME_CODE = re.compile(r"^\d{2}\.\d{2}\.\d{2}")
# A heading has to be a phrase. Below this it is a page letter, a column label
# or an artefact of the reflow ("E", "F", "H" all appeared as headings).
_MIN_HEADING_LETTERS = 3
# A numbered heading longer than this is a numbered *list item* -- an activity
# step or an instruction ("3. Stir the mixture thoroughly and put it", eight
# words). Six is a deliberate trade: it costs the occasional long chapter title
# ("5. Substances in the Surroundings - Their States and Properties"), which
# degrades to no heading rather than to a wrong one. A missed heading merges
# two sections; a spurious one splits a section AND mislabels the citation the
# student is shown, so the errors are not symmetric.
_MAX_NUMBERED_HEADING_WORDS = 6
_MAX_HEADING_CHARS = 90
# A heading may end in a question mark -- textbooks are full of them ("What
# are Tissues?", "Why do we fall ill?") -- so only the punctuation that ends
# a *sentence mid-prose* disqualifies a line.
#
# The danda (\u0964) and double danda (\u0965) are the Devanagari full stop, and
# leaving them out meant a plain Hindi sentence ending a paragraph
# ("\u0924\u0930\u093e\u0908 \u092e\u0947\u0902 \u0906\u092e\u0924\u094c\u0930 \u092a\u0930 \u092a\u093e\u0908 \u091c\u093e\u0924\u0940 \u0939\u0948\u0964") was read as a heading, and so became a
# hard cut. Measured 2026-09-14 on the Class 10 Hindi Geography book: 45-48%
# of its paragraphs were classified as headings, against 0-4% for the English
# Science books.
_SENTENCE_END = re.compile(r"[.,;:\u0964\u0965]$")
# A line this much shorter than the page's full measure ended its paragraph
# rather than wrapping. 0.78 is deliberately generous: a false split costs one
# extra paragraph boundary, a missed one merges two topics into a chunk.
_SHORT_LINE_RATIO = 0.78
# Which line IS the full measure. The longest line on the page was the obvious
# answer and is the wrong one: a two-column page holds a column of ~46-character
# body lines plus the odd full-width heading or table row, so max() put the
# threshold above every body line and each one closed a paragraph -- mid
# sentence, "\u0915\u093e\u0932\u0940 \u092e\u0943\u0926\u093e \u0915\u092a\u093e\u0938 \u0915\u0940 \u0916\u0947\u0924\u0940 \u0915\u0947 \u0932\u093f\u090f" ended one and "\u0909\u091a\u093f\u0924 \u0938\u092e\u091d\u0940 \u091c\u093e\u0924\u0940 \u0939\u0948"
# began the next. The 90th percentile is the widest line the BODY actually
# reaches, so a stray wide line no longer sets the bar for the page.
_FULL_MEASURE_PERCENTILE = 0.9
# Devanagari (Hindi, Marathi) plus the Devanagari extended block. Used to spot
# a script with no case distinction, where every capitalisation test below is
# vacuously false and would leave the numbered-heading regex as the only rule
# that can ever fire.
_DEVANAGARI = re.compile(r"[\u0900-\u097F\uA8E0-\uA8FF]")
# A caseless heading has to be short. Without case there is no other signal, so
# this is deliberately tighter than the 12-word Latin limit -- a wrong hard cut
# costs a merged topic and a mislabelled citation.
_MAX_CASELESS_HEADING_WORDS = 8
# ...and short in CHARACTERS, which is the test the word count could not make.
# A wrapped line of Hindi body text in a two-column textbook is 6-8 words and
# ~46 characters, so the word rule alone called half the book's paragraphs
# headings -- and every one of those is a hard cut, which is why the Geography
# book chunked to a median of 101 characters against a 1,200 target while the
# English Science books sat at 724.
#
# 30 characters keeps the real ones in these books ("\u0938\u092e\u0915\u093e\u0932\u0940\u0928 \u092d\u093e\u0930\u0924-2" 14,
# "\u0938\u0902\u0938\u093e\u0927\u0928 \u090f\u0935\u0902 \u0935\u093f\u0915\u093e\u0938" 16) and drops the wrapped prose. Measured
# 2026-09-14, pages 21-40 of that book: median chunk 101 -> 415 characters,
# 172 -> 79 chunks, with the English books character-identical.
_MAX_CASELESS_HEADING_CHARS = 30
# Words that appear in a figure or table label rather than a section heading.
# "Xylem Vessels" and "Fig. 6.2 Xylem Vessels" are both title-cased; only the
# second is reliably not a heading.
_LABEL_PREFIX = re.compile(
    r"^(fig|figure|table|chart|diagram|plate|box|activity|exercise|example)\b[\s.:]*",
    re.IGNORECASE,
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

    # Front matter, captions and contents pages, which a textbook has more of
    # than it has chapters. Every one of these was firing as a heading -- and
    # since a heading is a *hard cut*, each spurious one splits a section in
    # two and labels the remainder with a figure number. Measured on the
    # Class 6 Science book before this: 352 distinct headings across 419
    # chunks, median chunk 374 characters against a 1,200 target.
    if _DOT_LEADER.search(stripped) or _OUTCOME_CODE.match(stripped):
        return False
    if _FIGURE_CAPTION.match(stripped):
        return False
    if len([c for c in stripped if c.isalpha()]) < _MIN_HEADING_LETTERS:
        return False

    # A numbered section is the most reliable signal in any script, and the
    # only one that fires for Devanagari before the caseless branch below --
    # but only when it is short enough to be a heading rather than step 3 of
    # an activity.
    if _NUMBERED_HEADING.match(stripped):
        return len(stripped.split()) <= _MAX_NUMBERED_HEADING_WORDS
    words = stripped.split()
    if len(words) > 12:
        return False
    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return False

    # Devanagari has no case, so every test below this point is vacuously
    # false for a Hindi or Marathi book -- which left the numbered regex as
    # the only rule that could ever fire, and an unnumbered Devanagari chapter
    # heading merging silently into the paragraph before it.
    #
    # With no case to read, brevity is the only signal left: a short line that
    # does not end like a sentence, in a script where paragraphs do not look
    # like this.
    if _DEVANAGARI.search(stripped):
        return (len(words) <= _MAX_CASELESS_HEADING_WORDS
                and len(stripped) <= _MAX_CASELESS_HEADING_CHARS)

    if _LABEL_PREFIX.match(stripped):
        # "Fig. 6.2 Xylem Vessels" is a caption, not a section boundary.
        return False
    if all(c.isupper() for c in letters):
        return True

    # Title case alone is too weak. The old rule made *any* two capitalised
    # words a heading, so every figure label ("Xylem Vessels", "Cardiac
    # Muscle") became a hard cut -- splitting a section mid-explanation and
    # filing the remainder under the label instead of the chapter.
    #
    # Require enough words that the line reads as a heading rather than a
    # noun phrase lifted out of the prose around it.
    capitalised = sum(1 for w in words if w[:1].isupper())
    if len(words) < 3:
        return False
    return capitalised >= max(3, int(len(words) * 0.7))


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
    measured = sorted(len(l.strip()) for l in lines if l.strip())
    if not measured:
        return ""
    # The full measure is the widest line the body text reaches -- see
    # _FULL_MEASURE_PERCENTILE for why this is not simply max().
    full_measure = measured[min(len(measured) - 1,
                                int(len(measured) * _FULL_MEASURE_PERCENTILE))]
    threshold = full_measure * _SHORT_LINE_RATIO

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


def _page_text(page) -> str:
    """One page's plain text, with legacy-font Hindi converted to Unicode.

    A page with no legacy font takes exactly the old path. Otherwise the page
    is rebuilt from PyMuPDF's span list, line by line in the same order
    get_text() uses, and only spans set in a legacy font are converted --
    Arial digits and real English beside them are left alone. Consecutive
    legacy spans in a line are converted together, because the i-matra and the
    reph move across glyphs and a word can straddle a span boundary.
    """
    if not any(legacy_hindi.is_legacy_font(f[3]) for f in page.get_fonts()):
        return page.get_text() or ""
    lines = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            parts, run = [], []
            for span in line.get("spans", []):
                if legacy_hindi.is_legacy_font(span.get("font", "")):
                    run.append(span.get("text", ""))
                    continue
                if run:
                    parts.append(legacy_hindi.to_unicode("".join(run)))
                    run = []
                parts.append(span.get("text", ""))
            if run:
                parts.append(legacy_hindi.to_unicode("".join(run)))
            lines.append("".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")


def devanagari_share(pages: Sequence[str]) -> float:
    """Share of letters that are Devanagari, 0-1.

    A Hindi-medium book that comes out near 0 was set in a legacy font this
    pipeline does not recognise (NeoMitra, for one): the words are there but
    encoded as Latin symbols, so it will match nothing.
    """
    text = "\n".join(pages)
    deva = len(_DEVA_ANY.findall(text))
    latin = sum(1 for ch in text if ("a" <= ch <= "z") or ("A" <= ch <= "Z"))
    return deva / (deva + latin) if (deva + latin) else 0.0


def extract_pages(data: bytes) -> List[str]:
    """Raw per-page text, in reading order. Raises PdfExtractionError.

    PyMuPDF only. It replaced pypdf on 2026-09-10: pypdf ignores the ToUnicode
    maps of NCERT's Hindi subset fonts and returns valid-looking Devanagari that
    is the wrong words. Measured on ehve101.pdf, page 3:

        pypdf    "किरन ने ्ूसरी ्ुकनया में जाने िी िात कयों िही होगी?"
        pymupdf  "किरन ने दूसरी दुनिया में जाने की बात कयों कही होगी?"

    English came back character-identical either way, and pypdf also returned
    some text layers twice (42 duplicate chunk groups across the Class 5
    Science books), so nothing was lost by dropping it. PyMuPDF also reports
    each span's font, which is what lets legacy Chanakya/Kruti text be
    converted (see _page_text).
    """
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise PdfExtractionError(
            "PyMuPDF is not installed. Run: pip install -r requirements.txt"
        ) from exc

    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            # An empty password unlocks the common "no printing" case; a real
            # password is a genuine failure the user has to resolve.
            if doc.needs_pass and not doc.authenticate(""):
                raise PdfExtractionError(
                    "This PDF is password-protected. Remove the password and try again."
                )
            return [_page_text(page) for page in doc]
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


# -- Devanagari integrity --------------------------------------------------
#
# A broken font map produces *valid* Devanagari that is the wrong words, so
# nothing downstream can see the problem: the text has the right script, the
# right length and the right punctuation, it embeds without complaint, and it
# retrieves nothing. The first Hindi corpus loaded here was 100% corrupt and
# the only symptom was "Hindi accuracy is poor".
#
# What gives it away is structure rather than vocabulary, which means no
# dictionary and no word list. Devanagari has combining signs that can only
# ever follow a consonant, so a matra opening a token, two viramas in a row,
# or a matra separated from its consonant by a space are all *impossible* in
# correctly encoded text -- and all common in mis-decoded text.
_DEVA_DEPENDENT = "ा-ॏॕ-ॗॢॣ"
_DEVA_VIRAMA = "्"
_DEVA_ANY = re.compile(r"[ऀ-ॿ]")

_DEVA_BREAKAGE = (
    # A dependent sign opening a whitespace-delimited token: "िरते", "्ूसरी".
    re.compile(r"(?:^|\s)[" + _DEVA_DEPENDENT + _DEVA_VIRAMA + r"]"),
    # Two viramas with nothing between them: "शब््ों".
    re.compile(_DEVA_VIRAMA + r"\s*" + _DEVA_VIRAMA),
    # A virama followed by a matra -- no consonant to carry either.
    re.compile(_DEVA_VIRAMA + r"[" + _DEVA_DEPENDENT + r"]"),
    # A matra orphaned between spaces: "क े", "वाल े".
    re.compile(r"\s[" + _DEVA_DEPENDENT + r"](?:\s|$)"),
    # A virama ending a token, with no following consonant to join.
    re.compile(_DEVA_VIRAMA + r"(?:\s|$)"),
)

# Breakages per 100 Devanagari characters. Clean NCERT text measured 0.0-0.3
# (a genuine trailing virama in "सम्" style abbreviations is rare but real);
# every mis-decoded book measured 4.4-7.3. The gap is wide enough that the
# threshold does not need to be precise.
_DEVA_BREAKAGE_LIMIT = 1.5
# Below this there is not enough Devanagari to judge -- an English book with a
# few Hindi terms in it must not trip the check.
_DEVA_MIN_CHARS = 400


def devanagari_breakage_rate(pages: Sequence[str]) -> Optional[float]:
    """Structural breakages per 100 Devanagari characters, or None.

    None means "not enough Devanagari to have an opinion", which is not the
    same as zero and must not be compared against the limit.
    """
    text = "\n".join(pages)
    total = len(_DEVA_ANY.findall(text))
    if total < _DEVA_MIN_CHARS:
        return None
    breakages = sum(len(rx.findall(text)) for rx in _DEVA_BREAKAGE)
    return breakages / total * 100.0


def looks_mis_decoded(pages: Sequence[str]) -> bool:
    """True when the Devanagari in this PDF did not survive extraction."""
    rate = devanagari_breakage_rate(pages)
    return rate is not None and rate > _DEVA_BREAKAGE_LIMIT


# `devanagari_breakage_rate` only ever looks inside the Devanagari block
# (ऀ-ॿ), on the assumption that a broken font map still lands on *some*
# Devanagari codepoint -- true for Chanakya/Kruti-style fonts, which are
# themselves "Hindi-shaped". It is not true in general: found 2026-09-18
# fetching a Class 6 Geography replacement from a third-party mirror, whose
# extracted "Hindi" text was entirely Dingbats-block symbols (✐✁✂✄...,
# U+2700-27BF) -- a proprietary font's glyph IDs read through a missing or
# wrong ToUnicode map, same root failure as the pypdf bug this project
# already fixed once, just landing somewhere `looks_mis_decoded` cannot see
# at all (zero Devanagari codepoints -> `devanagari_breakage_rate` returns
# None -> no warning, ever). Caught by hand that time, by actually reading
# the extracted text before trusting it -- this check is what makes that
# unnecessary going forward.
#
# Script-agnostic on purpose: rather than enumerate every symbol/private-use
# range a broken font map could land in, this asks the opposite question --
# how much of the "text" is NOT in a script this library ever teaches in
# (Latin or Devanagari), and not ordinary punctuation either? A normal book,
# in any mix of English/Hindi/Marathi, scores near 0. A font-glyph dump scores
# near 1.
#
# Punctuation is allow-listed explicitly rather than matched with `\w`:
# Python's `\w` follows Unicode's alphanumeric property, which excludes the
# Dingbats block (category So, "Symbol, other") entirely -- the first version
# of this check used `\w` to find "letterlike" characters and it matched
# nothing at all in the garbage sample, so the ratio was computed over zero
# candidates and never tripped. Counting non-whitespace characters directly,
# with punctuation allow-listed, is what actually classifies a dingbat as
# "not expected" instead of silently excluding it from consideration.
_EXPECTED_CHAR = re.compile(
    r"[A-Za-zऀ-ॿ0-9.,!?;:'\"()\[\]{}\-–—/%&@#*+=<>~`|_]"
)
# Below this many non-whitespace characters the ratio is noise -- a title
# page or a handful of section numbers must not trip the check.
_GARBAGE_MIN_CHARS = 400
# Clean books (English, Hindi, Marathi, or a mix) measure near 0. A pure
# symbol-font dump measures near 1; this sits well below that gap rather than
# at its edge, the same margin `_DEVA_BREAKAGE_LIMIT` uses.
_GARBAGE_SCRIPT_LIMIT = 0.15


def looks_like_garbage_script(pages: Sequence[str]) -> bool:
    """True when the "text" is mostly characters outside every script this
    library actually teaches in -- a symbol/dingbat font masquerading as text,
    carrying zero recoverable information. Treated the same as
    `looks_like_scan`: this is not degraded text, it is no text.
    """
    text = "\n".join(pages)
    non_space = [ch for ch in text if not ch.isspace()]
    if len(non_space) < _GARBAGE_MIN_CHARS:
        return False
    expected = sum(1 for ch in non_space if _EXPECTED_CHAR.match(ch))
    return (1 - expected / len(non_space)) > _GARBAGE_SCRIPT_LIMIT


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
