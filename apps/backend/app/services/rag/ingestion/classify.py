"""
Stage 6 -- content classification.

Chunking a table the way you chunk a paragraph destroys it, and
splitting an exercise between its question and its answer makes
both useless. So before chunking we label each block with what it
is, using geometry and typography rather than the text alone --
those survive translation between languages, which keyword lists
do not.

Every decision records its evidence, because these heuristics will
need tuning against real textbooks and untraceable guesses cannot
be tuned.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Any

from .model import BBox, Block, Document, Page

# A heading is typographically louder than the body text.
HEADING_SIZE_RATIO = 1.15
HEADING_MAX_CHARS = 140
HEADING_MAX_LINES = 3

CAPTION_MAX_CHARS = 300
CAPTION_GAP = 45.0          # points between an image and its caption

PARAGRAPH_MIN_CHARS = 40

# Section headers for exercises, in both languages we handle today.
_EXERCISE_RE = re.compile(
    r"^\s*(exercises?|questions?|activity|activities|practice"
    r"|अभ्यास"          # अभ्यास
    r"|प्रश्नावली"  # प्रश्नावली
    r"|प्रश्न"          # प्रश्न
    r"|क्रियाकलाप"  # क्रियाकलाप
    r")\b",
    re.IGNORECASE,
)

# "Q.1", "1.", "(iii)", "(अ)" at the head of a block.
_QUESTION_RE = re.compile(
    r"^\s*(?:Q\.?\s*\d+|\(?\d{1,2}[.)]|\(?[ivx]{1,4}[.)]"
    r"|\(?[अ-औ][.)])\s+",
    re.IGNORECASE,
)

# Devanagari sentences end in a danda, not a question mark, so a
# Hindi question is recognised by its interrogative rather than its
# punctuation.
_HINDI_INTERROGATIVE = re.compile(
    r"कौन|क्या|किस|"     # कौन, क्या, किस
    r"क्यों|कैसे|"           # क्यों, कैसे
    r"कहाँ|कितन"                  # कहाँ, कितन
)

# Multiple-choice option labels: "(क) ... (ख) ..." or "(a) ... (b)".
# Two or more in one block is the giveaway.
_MCQ_OPTIONS = re.compile(
    r"\(\s*(?:[क-घ]|[a-dA-D]|[ivx]{1,3})\s*\)"
)
MIN_MCQ_OPTIONS = 2

_CAPTION_RE = re.compile(
    r"^\s*(fig(ure)?|table|map|chart|plate|image|source"
    r"|चित्र"                # चित्र
    r"|सारणी"                # सारणी
    r"|तालिका"          # तालिका
    r"|आकृति"                # आकृति
    r")\b[\s.:–-]*\d*",
    re.IGNORECASE,
)

_LIST_RE = re.compile(r"^\s*(?:[•▪◦‣⁃*–—-]|\(?[a-z][.)]|\(?\d{1,2}[.)])\s+")

_MATH_CHARS = set("=+−×÷^√∑∫≤≥≠<>/±πΔθ()[]{}|")

_SENTENCE_END = re.compile(r"[.!?।॥]\s*$")

# Sentence TERMINATORS anywhere in a block, not just at its end. Counting them
# is how a caption ('चित्र 1.7 — काली मृदा') is told apart from the paragraph
# printed beneath the same figure. The danda is included: it is the Devanagari
# full stop, and omitting it would make every Hindi paragraph look like a
# single unterminated phrase, i.e. exactly like a caption.
_SENTENCE_SPLIT_RE = re.compile(r"[.!?।॥]")


@dataclass
class PageContext:
    """Page-level typography, used to judge blocks relative to it."""

    median_size: float = 10.0
    page_width: float = 612.0
    page_height: float = 792.0
    image_boxes: list[BBox] = field(default_factory=list)


def build_context(page: Page) -> PageContext:
    """Measure the page's body text so blocks can be compared to it."""
    sizes: list[float] = []

    for block in page.text_blocks:
        for line in block.lines:
            for span in line.spans:
                if span.text.strip():
                    # Weight by length so a big title does not drag
                    # the "body size" upwards.
                    sizes.extend([span.size] * len(span.text.strip()))

    return PageContext(
        median_size=statistics.median(sizes) if sizes else 10.0,
        page_width=page.width,
        page_height=page.height,
        image_boxes=[block.bbox for block in page.blocks if block.kind == "image"],
    )


def _column_alignment_score(block: Block) -> float:
    """
    Fraction of lines that share a repeated set of x-start positions.

    Table rows line up; wrapped prose does not.
    """
    multi_span_lines = [line for line in block.lines if len(line.x_starts) >= 2]
    if len(multi_span_lines) < 2:
        return 0.0

    # Round to a 4pt grid so minor kerning differences still match.
    signatures = [
        tuple(round(x / 4) for x in sorted(line.x_starts)[:6])
        for line in multi_span_lines
    ]

    counts: dict[tuple, int] = {}
    for signature in signatures:
        counts[signature] = counts.get(signature, 0) + 1

    return max(counts.values()) / len(block.lines)


def _near_image(block: Block, context: PageContext) -> bool:
    """True if the block sits directly above or below a figure."""
    x0, y0, x1, y1 = block.bbox

    for ix0, iy0, ix1, iy1 in context.image_boxes:
        horizontal_overlap = min(x1, ix1) - max(x0, ix0)
        if horizontal_overlap <= 0:
            continue
        if 0 <= y0 - iy1 <= CAPTION_GAP or 0 <= iy0 - y1 <= CAPTION_GAP:
            return True

    return False


def _math_ratio(text: str) -> float:
    visible = [char for char in text if not char.isspace()]
    if not visible:
        return 0.0
    hits = sum(1 for char in visible if char in _MATH_CHARS or char.isdigit())
    return hits / len(visible)


def classify_block(block: Block, context: PageContext) -> tuple[str, float, dict[str, Any]]:
    """Return (content_type, confidence, evidence) for one block."""
    if block.kind == "image":
        return "image", 1.0, {"reason": "pdf_image_block"}

    text = (block.normalized_text or block.text).strip()
    evidence: dict[str, Any] = {
        "chars": len(text),
        "lines": len(block.lines),
        "max_size": block.max_size,
        "median_page_size": round(context.median_size, 2),
        "bold": block.is_bold,
    }

    if not text:
        return "other", 0.0, {**evidence, "reason": "empty"}

    # --- table ----------------------------------------------------
    alignment = _column_alignment_score(block)
    evidence["column_alignment"] = round(alignment, 2)
    if alignment >= 0.5 and len(block.lines) >= 3:
        return "table", round(min(0.5 + alignment / 2, 0.95), 2), {
            **evidence,
            "reason": "repeated_column_alignment",
        }

    # --- exercise -------------------------------------------------
    # Caught before anything else, and deliberately broadly: a
    # multiple-choice block is mostly *wrong* answers, and one read
    # as prose will be quoted back to a student as fact. Over-tagging
    # a paragraph as an exercise loses one passage; under-tagging an
    # exercise puts distractors into the answer.
    if _EXERCISE_RE.match(text):
        return "exercise", 0.9, {**evidence, "reason": "exercise_heading"}

    options = len(_MCQ_OPTIONS.findall(text))
    evidence["mcq_options"] = options
    if options >= MIN_MCQ_OPTIONS:
        return "exercise", 0.85, {**evidence, "reason": "multiple_choice_options"}

    if _QUESTION_RE.match(text) and (
        "?" in text or _HINDI_INTERROGATIVE.search(text)
    ):
        return "exercise", 0.75, {**evidence, "reason": "numbered_question"}

    # --- formula --------------------------------------------------
    math_ratio = _math_ratio(text)
    evidence["math_ratio"] = round(math_ratio, 2)
    if math_ratio >= 0.4 and len(text) < 200 and any(c in text for c in "=+−×÷"):
        return "formula", 0.7, {**evidence, "reason": "symbol_dense"}

    size_ratio = block.max_size / context.median_size if context.median_size else 1.0
    evidence["size_ratio"] = round(size_ratio, 2)

    # --- caption (labelled) ---------------------------------------
    # "चित्र 1.7 — काली मृदा" names itself. Strong enough to beat everything.
    if len(text) <= CAPTION_MAX_CHARS and _CAPTION_RE.match(text):
        return "caption", 0.85, {**evidence, "reason": "caption_label"}

    # --- heading --------------------------------------------------
    # BEFORE proximity-captioning, deliberately. These NCERT pages carry three
    # or four figures each, and `_near_image` claims anything whose horizontal
    # span overlaps a figure within CAPTION_GAP -- which on such a page is most
    # of the text, including the section headings printed between figures.
    #
    # Measured 2026-09-22 on Class 10 Geography p25-26: the heading "वन मृदा"
    # and the opening line of "मृदा अपरदन और संरक्षण" were both classified
    # `caption`. A caption never calls `start_section` (see chunk.SKIP and
    # chunk_document), so every chunk after a swallowed heading inherited the
    # PREVIOUS section: the whole soil-erosion and soil-conservation run,
    # ordinals 247-269, was filed under "मरुस्थली मृदा". Headings are embedded
    # (`embedding_text` prepends the breadcrumb), so that mislabelling did not
    # merely produce a wrong citation -- it poisoned the vectors and is why
    # "मृदा संरक्षण के उपाय" could not retrieve its own answer at any k.

    if (
        len(text) <= HEADING_MAX_CHARS
        and len(block.lines) <= HEADING_MAX_LINES
        and not _SENTENCE_END.search(text)
    ):
        if size_ratio >= HEADING_SIZE_RATIO:
            return "heading", 0.85, {**evidence, "reason": "larger_than_body"}
        if block.is_bold:
            return "heading", 0.7, {**evidence, "reason": "bold_short_line"}
        if text.isupper() and len(text) > 3:
            return "heading", 0.65, {**evidence, "reason": "all_caps"}

    # --- caption (by position) ------------------------------------
    # Runs only after a block has failed to be a heading. Proximity is the
    # weakest evidence there is -- it says where a block sits, not what it is --
    # so it is fenced twice:
    #
    #   one sentence at most : a real caption labels a figure. The block that
    #       cost us the erosion section was three sentences of prose that
    #       happened to be printed under 'चित्र 1.10'. Prose is not a caption
    #       however close to a figure it sits.
    #   not larger than body : a caption is set at or below body size. Anything
    #       typographically louder has already been offered to the heading rule
    #       above and refused it for some other reason; it is not a caption.
    if (
        len(text) <= CAPTION_MAX_CHARS
        and len(_SENTENCE_SPLIT_RE.findall(text)) <= 1
        and size_ratio < HEADING_SIZE_RATIO
        and _near_image(block, context)
    ):
        return "caption", 0.6, {**evidence, "reason": "adjacent_to_image"}

    # --- list -----------------------------------------------------
    if _LIST_RE.match(text):
        return "list_item", 0.7, {**evidence, "reason": "list_marker"}

    # --- paragraph ------------------------------------------------
    if len(text) >= PARAGRAPH_MIN_CHARS:
        return "paragraph", 0.8, {**evidence, "reason": "prose_length"}

    return "other", 0.4, {**evidence, "reason": "too_short_to_classify"}


def classify_page(page: Page) -> None:
    context = build_context(page)

    for block in page.blocks:
        content_type, confidence, evidence = classify_block(block, context)
        block.content_type = content_type
        block.content_confidence = confidence
        block.classification_evidence = evidence


def classify_document(document: Document) -> dict[str, int]:
    counts: dict[str, int] = {}

    for page in document.pages:
        classify_page(page)
        for block in page.blocks:
            counts[block.content_type] = counts.get(block.content_type, 0) + 1

    return counts
