"""
Stage 2 -- columns and reading order.

A textbook page is rarely one top-to-bottom flow. Two-column pages
are common, and a full-width heading usually sits above them. Read
such a page naively and a sentence from the left column gets glued
to an unrelated sentence from the right -- which then embeds as one
chunk and poisons retrieval.

The approach here is a vertical projection: find a whitespace
gutter that runs down the page, and split on it. Blocks that cross
the gutter are treated as full-width and act as band separators.
"""

from __future__ import annotations

from .model import BBox, Block, Line, Page

# A gutter must be at least this fraction of the content width to count
# as a column separator rather than ordinary word spacing.
#
# 0.035 -> 0.025 on 2026-09-21. The Class 10 Geography book's gutter is 18pt on
# a 474pt text width (3.8%), but the histogram marks the bin each box ends in,
# so a gap loses about a bin at each edge and page 26 measured 3.0% -- rejected,
# read as ONE column, and its right-hand heading "मृदा अपरदन और संरक्षण" was
# interleaved among the left column's blocks, so the sentence "इसे समोच्च जुताई
# कहा जाता है" was filed under "मरुस्थली मृदा". 2.5% of that width is still
# ~12pt against 3-6pt of word spacing, and the per-column character minimum and
# the vertical-overlap check below still have to pass.
MIN_GUTTER_RATIO = 0.025

# ...and must sit in the middle of the content, not near an edge.
GUTTER_SEARCH_BAND = (0.25, 0.75)

# Each side of the gutter needs this much text before we believe it,
# so that a stray page number or marginal note cannot invent a column.
MIN_CHARS_PER_COLUMN = 80

# Real columns run alongside each other. A figure beside its caption
# does not, and should stay a single flow.
MIN_VERTICAL_OVERLAP = 0.5

# Resolution of the projection histogram.
_BINS = 200

# A box wider than this share of the content width is full-measure, and is
# excluded from the gutter projection.
#
# It has to be. A gutter is found as a run of horizontal whitespace, and one
# full-width line lays ink right across the gap -- so a single spanning
# element (a heading, a figure caption, the "(a) Punjab (b) Haryana ..."
# line of a multiple-choice question) masks the gutter for the whole page and
# the two columns beside it are read as one flow.
#
# Measured while porting: a synthetic two-column page reported its gutter at
# x=263 with only the body present, and no gutter at all once the exercise
# lines beneath it were included. Real textbook pages mix the two constantly.
#
# Excluded from the PROJECTION only. Spanning blocks are still classified
# SPANNING afterwards and still act as band separators in reading order,
# which is what they are for.
_MAX_BOX_WIDTH_RATIO = 0.6

# Column marker for a block that spans the full content width.
SPANNING = -1


def _boxes(blocks: list[Block]) -> list[BBox]:
    """The boxes the gutter projection is measured over: LINES, not blocks.

    Upstream projected block boxes, and on this corpus that finds nothing.
    PyMuPDF does not return one block per column -- it returns one block per
    *paragraph band*, with the left column's line and the right column's line
    as two lines inside it:

        BLOCK 0 bbox=(60, 98, 390, 113)
           LINE 0 bbox=(60, 98, 121, 113)   'left one AAA'
           LINE 1 bbox=(320, 98, 390, 113)  'right one CCC'

    That block box spans the gutter, so a block-level projection sees the full
    width covered, finds no whitespace run, and reports a single column. The
    two columns are then read as one flow and glued into one paragraph -- which
    is the 42% of chunks carrying a mid-sentence paragraph break measured on
    the live library (2026-09-20).

    Line boxes show the gutter plainly. A block with no lines (an image, or a
    reconstructed formula) contributes its own box.
    """
    boxes: list[BBox] = []
    for block in blocks:
        if block.lines:
            boxes.extend(line.bbox for line in block.lines)
        else:
            boxes.append(block.bbox)
    return boxes


def _coverage(boxes: list[BBox], left: float, right: float) -> list[int]:
    """How MANY boxes cover each horizontal bin, over the extent [left, right].

    A count rather than a boolean, and that difference decides whether column
    detection works on a real textbook at all.

    A gutter is a column of white space, but "white" is not the same as
    "untouched": one stray element laid across it -- a footer, a figure, a
    wide caption -- makes every bin in the gap covered, and a boolean
    projection then reports a single-column page. Measured on the Class 10
    Geography book: page 25 is plainly two columns (78-306 and 324-552), and
    the string "2019-2020" printed at x=286.9 straddles the gap and hid the
    gutter. Only 2 of 112 pages were detected as two-column.

    Counting instead leaves the gutter as a VALLEY -- a couple of crossing
    boxes against fifteen lines per column -- which survives the noise.

    The extent is passed in rather than measured from `boxes`, because the
    boxes that define how wide the text area is are not the same set as the
    boxes the gutter is looked for among -- see `_MAX_BOX_WIDTH_RATIO`.
    """
    counts = [0] * _BINS
    span = max(right - left, 1e-6)

    for box in boxes:
        start = int((box[0] - left) / span * (_BINS - 1))
        end = int((box[2] - left) / span * (_BINS - 1))
        for index in range(max(0, start), min(_BINS, end + 1)):
            counts[index] += 1

    return counts


# A gutter bin may be crossed by at most this share of the busiest bin's
# boxes. Low enough that the space BETWEEN two columns still reads as a
# valley, high enough to tolerate a few elements laid across it.
_GUTTER_MAX_COVERAGE = 0.2


def find_gutter(page: Page) -> float | None:
    """
    Return the x coordinate of a column gutter, or None for a
    single-column page.
    """
    blocks = [block for block in page.text_blocks if block.text.strip()]
    if len(blocks) < 2:
        return None

    boxes = _boxes(blocks)
    if len(boxes) < 2:
        return None

    # Content extent is measured over every box, including the full-width
    # ones -- they define how wide the page's text area is. Only the
    # projection drops them.
    left = min(box[0] for box in boxes)
    right = max(box[2] for box in boxes)
    content_width = right - left
    if content_width <= 0:
        return None

    narrow = [
        box for box in boxes
        if (box[2] - box[0]) <= _MAX_BOX_WIDTH_RATIO * content_width
    ]
    if len(narrow) < 2:
        return None

    counts = _coverage(narrow, left, right)

    # Longest LOW-COVERAGE run inside the central search band.
    low = int(GUTTER_SEARCH_BAND[0] * _BINS)
    high = int(GUTTER_SEARCH_BAND[1] * _BINS)

    busiest = max(counts) if counts else 0
    if busiest <= 0:
        return None
    ceiling = max(0, int(_GUTTER_MAX_COVERAGE * busiest))

    best_run = (0, 0)
    run_start = None

    for index in range(low, high + 1):
        if counts[index] <= ceiling:
            if run_start is None:
                run_start = index
        else:
            if run_start is not None:
                if index - run_start > best_run[1] - best_run[0]:
                    best_run = (run_start, index)
                run_start = None

    if run_start is not None and (high + 1) - run_start > best_run[1] - best_run[0]:
        best_run = (run_start, high + 1)

    run_width = best_run[1] - best_run[0]
    if run_width / _BINS < MIN_GUTTER_RATIO:
        return None

    centre_bin = (best_run[0] + best_run[1]) / 2
    gutter_x = left + (centre_bin / (_BINS - 1)) * content_width

    # Confirm the split actually separates content on both sides. Measured
    # over LINES for the reason in `_boxes`: when PyMuPDF has merged the two
    # columns into one block, no block falls wholly on either side and a
    # block-level confirmation rejects every real gutter it was just handed.
    lines = [line for block in blocks for line in block.lines if line.text.strip()]
    if not lines:
        return None

    left_side = [line for line in lines if line.bbox[2] <= gutter_x]
    right_side = [line for line in lines if line.bbox[0] >= gutter_x]

    if not left_side or not right_side:
        return None

    if (
        sum(len(line.text) for line in left_side) < MIN_CHARS_PER_COLUMN
        or sum(len(line.text) for line in right_side) < MIN_CHARS_PER_COLUMN
    ):
        return None

    if _vertical_overlap(left_side, right_side) < MIN_VERTICAL_OVERLAP:
        return None

    return gutter_x


def _vertical_overlap(left: list, right: list) -> float:
    """
    How much the two sides share vertical space, as a fraction of
    the shorter one.

    Takes anything carrying a `bbox`: blocks or lines.
    """
    left_top = min(item.bbox[1] for item in left)
    left_bottom = max(item.bbox[3] for item in left)
    right_top = min(item.bbox[1] for item in right)
    right_bottom = max(item.bbox[3] for item in right)

    overlap = min(left_bottom, right_bottom) - max(left_top, right_top)
    shorter = min(left_bottom - left_top, right_bottom - right_top)

    if shorter <= 0:
        return 0.0

    return max(0.0, overlap / shorter)


def _side_of(box: BBox, gutter_x: float) -> int:
    """Which column a box belongs to: 0, 1, or SPANNING."""
    x0, _, x1, _ = box
    if x0 < gutter_x < x1:
        return SPANNING
    return 0 if x1 <= gutter_x else 1


# A vertical gap larger than this share of the line height starts a new
# paragraph. Within a paragraph the gap between lines is the leading, a small
# fraction of the line height; between paragraphs it is the leading plus the
# space the designer put there.
PARAGRAPH_GAP_RATIO = 0.6


def group_lines_into_paragraphs(lines: list[Line]) -> list[list[Line]]:
    """Group a column's lines into paragraphs, by the gap between them.

    This is the step that makes the rest of the pipeline work, and leaving it
    out broke the first re-ingest of the live corpus.

    `normalize.join_soft_wraps` rejoins lines that the layout wrapped, and it
    works WITHIN a block. `chunk.split_sentences` then splits the result into
    sentences. Both depend on a block holding a run of consecutive lines.

    Splitting at the gutter destroys that if it is done per block: PyMuPDF
    hands back one block per paragraph BAND, holding the left column's line
    and the right column's line, so splitting each block in place yields one
    block per LINE. There is then nothing to rejoin, every line fragment is
    treated as a sentence, and chunks break wherever the printed line broke:

        ord=297  ...इनका पीला रंग इनमें जलयोजन के कारण होता है। काली मृदा
        ord=298  काली मृदा इन मृदाओं का रंग काला है और इन्हे 'रेगर' ...
        ord=299  कहा जाता है। काली मृदा कपास की खेती के लिए उचित समझी ...

    Every one of those ends mid-sentence, and the sentence-overlap carries the
    fragment into the next chunk. A passage that stops mid-sentence is exactly
    what the model cannot answer from.
    """
    if not lines:
        return []

    ordered = sorted(lines, key=lambda line: (round(line.bbox[1], 1), line.bbox[0]))
    heights = sorted(line.bbox[3] - line.bbox[1] for line in ordered)
    line_height = heights[len(heights) // 2] or 1.0
    limit = PARAGRAPH_GAP_RATIO * line_height

    groups: list[list[Line]] = [[ordered[0]]]
    for previous, line in zip(ordered, ordered[1:]):
        if line.bbox[1] - previous.bbox[3] > limit:
            groups.append([line])
        else:
            groups[-1].append(line)
    return groups


def split_blocks_at_gutter(page: Page, gutter_x: float) -> int:
    """Split blocks whose lines straddle the gutter. Returns blocks added.

    This is what actually repairs a two-column page, and it has no counterpart
    upstream, where tagging a block with a column was enough because blocks
    were assumed to be per-column already.

    They are not. PyMuPDF groups a left-column line and the right-column line
    beside it into one block (see `_boxes`), so the two columns interleave
    line by line inside it. Tagging that block does nothing -- whichever
    column it is assigned to, its text still reads

        "These soils are black in colour and are | These soils are found in
         the north west | also called regur soils. Black soil is | Deccan
         plateau and are made of lava"

    and normalization then joins those alternating halves into one paragraph
    of fluent nonsense, which embeds as nonsense and is quoted to a student as
    fact. Splitting the block into one block per side, each keeping its own
    lines in order, is the only point at which the two flows can still be told
    apart -- after this stage the geometry is gone.

    A line that itself crosses the gutter (a full-width heading inside an
    otherwise two-column band) stays with the spanning group.
    """
    side_lines: dict[int, list[Line]] = {}
    passthrough: list[Block] = []

    for block in page.blocks:
        if block.kind != "text" or not block.lines:
            # Images, and the reconstructed-fraction blocks that carry text but
            # no lines, keep their own geometry and are never regrouped.
            passthrough.append(block)
            continue
        for line in block.lines:
            if line.text.strip():
                side_lines.setdefault(_side_of(line.bbox, gutter_x), []).append(line)

    if len(side_lines) < 2:
        return 0

    rebuilt: list[Block] = list(passthrough)
    for side in sorted(side_lines, key=lambda s: (s == SPANNING, s)):
        for group in group_lines_into_paragraphs(side_lines[side]):
            text = "\n".join(line.text for line in group if line.text.strip())
            if not text.strip():
                continue
            rebuilt.append(
                Block(
                    index=0,
                    kind="text",
                    bbox=(
                        min(line.bbox[0] for line in group),
                        min(line.bbox[1] for line in group),
                        max(line.bbox[2] for line in group),
                        max(line.bbox[3] for line in group),
                    ),
                    lines=list(group),
                    text=text,
                )
            )

    added = len(rebuilt) - len(page.blocks)
    # `index` is a tie-break in reading order and a label in the report; it has
    # to stay unique after regrouping.
    for index, block in enumerate(rebuilt):
        block.index = index
    page.blocks = rebuilt
    return added


def assign_columns(page: Page, gutter_x: float | None = None) -> int:
    """
    Tag every block with a column index and return the column count.

    Column 0 is left, 1 is right, and SPANNING marks a block that
    crosses the gutter (typically a title or a wide figure).
    """
    if gutter_x is None:
        gutter_x = find_gutter(page)

    if gutter_x is None:
        for block in page.blocks:
            block.column = 0
        page.column_count = 1
        return 1

    for block in page.blocks:
        x0, _, x1, _ = block.bbox
        if x0 < gutter_x < x1:
            block.column = SPANNING
        elif x1 <= gutter_x:
            block.column = 0
        else:
            block.column = 1

    page.column_count = 2
    return 2


def _vertically_overlaps(a: Block, b: Block) -> bool:
    return min(a.bbox[3], b.bbox[3]) > max(a.bbox[1], b.bbox[1])


def two_column_span(blocks: list[Block]) -> tuple[float, float] | None:
    """The y-range over which the two columns actually run alongside each other.

    Computed from PAIRS of blocks that genuinely overlap, never from each
    column's overall extent. Both alternatives were tried and both are wrong:

      min/max per column   one stray block blows it open. A folio printed at
                           x=290 -- right of the gutter, 600 points below the
                           body -- put the whole lower page "inside" the
                           two-column zone, so an exercise heading there was
                           read as more of column 0 and emitted BEFORE the
                           right-hand column.

      per-block "is anything beside me?"
                           fragments the page. A block with no neighbour
                           opened its own band, which split one column into
                           several bands and interleaved them: page 25 of the
                           Geography book emitted left-y82, right-y82,
                           left-y397 -- so the passage naming the states where
                           black soil is found landed under the PREVIOUS
                           section's heading.

    A pair that overlaps is direct evidence of side-by-side text, and a block
    with no counterpart contributes nothing either way.
    """
    left = [b for b in blocks if b.column == 0]
    right = [b for b in blocks if b.column == 1]
    if not left or not right:
        return None

    tops: list[float] = []
    bottoms: list[float] = []
    for a in left:
        for b in right:
            if min(a.bbox[3], b.bbox[3]) > max(a.bbox[1], b.bbox[1]):
                tops.append(min(a.bbox[1], b.bbox[1]))
                bottoms.append(max(a.bbox[3], b.bbox[3]))

    return (min(tops), max(bottoms)) if tops else None


def order_blocks(page: Page) -> None:
    """
    Sort blocks into reading order and write `block.order`.

    Full-width blocks and anything outside the two-column zone split the page
    into horizontal bands; within a band we read the left column fully, then
    the right.
    """
    blocks = sorted(page.blocks, key=lambda b: (round(b.bbox[1], 1), b.bbox[0]))
    span = two_column_span(blocks)

    def interleaved(block: Block) -> bool:
        """Does this block belong to the side-by-side part of the page?"""
        if block.column == SPANNING or span is None:
            return False
        middle = (block.bbox[1] + block.bbox[3]) / 2
        return span[0] <= middle <= span[1]

    band = 0
    banded: list[tuple[int, int, float, float, Block]] = []

    for block in blocks:
        if block.kind == "image" and block.column == SPANNING:
            # A picture that happens to cross the gutter is not a separator.
            # Measured 2026-09-21 on page 25 of the Class 10 Geography book: a
            # full-page background raster and a figure frame (x 71-526) both
            # "spanned" the gutter, each opened a band, and the page was read
            # left-top, right-top, [image], left-bottom, right-bottom. The right
            # column's first block ("ये मृदाएँ महाराष्ट्र, सौराष्ट्र... पर पाई
            # जाती हैं") was emitted BEFORE the left column's "काली मृदा" heading,
            # so the sentence naming where black soil is found was filed under
            # the previous section, "जलोढ़ मृदा". Only text that spans the
            # gutter (a title) really cuts the page in two. The image stays with
            # the left column at its own height, where it does no harm.
            banded.append((band, 0, block.bbox[1], block.bbox[0], block))
        elif not interleaved(block):
            # A spanning block, or one above or below the columns: it opens a
            # new band and sits alone at its top.
            band += 1
            banded.append((band, -1, block.bbox[1], block.bbox[0], block))
            band += 1
        else:
            banded.append((band, block.column, block.bbox[1], block.bbox[0], block))

    banded.sort(key=lambda item: (item[0], item[1], item[2], item[3]))

    for order, item in enumerate(banded):
        item[4].order = order

    page.blocks = [item[4] for item in banded]


# A run-in heading is short. Longer than this and a bold lead-in sentence
# would be mistaken for one.
RUN_IN_HEADING_MAX_CHARS = 90

# ...and typographically louder than the lines under it, by weight or by size.
RUN_IN_HEADING_SIZE_RATIO = 1.15

_TERMINAL = ".!?।॥,;:"


def _line_is_bold(line: Line) -> bool:
    spans = [span for span in line.spans if span.text.strip()]
    return bool(spans) and all(span.bold for span in spans)


def _line_size(line: Line) -> float:
    sizes = [span.size for span in line.spans if span.text.strip()]
    return max(sizes) if sizes else 0.0


def _is_run_in_heading(first: Line, rest: list[Line]) -> bool:
    text = first.text.strip()
    if not text or len(text) > RUN_IN_HEADING_MAX_CHARS:
        return False
    if text[-1] in _TERMINAL:
        return False

    body = [line for line in rest if line.text.strip()]
    if not body:
        return False

    # Louder by weight: bold against body that is not.
    if _line_is_bold(first) and not any(_line_is_bold(line) for line in body):
        return True

    # ...or louder by size.
    body_size = sorted(_line_size(line) for line in body)[len(body) // 2]
    return bool(body_size) and _line_size(first) >= RUN_IN_HEADING_SIZE_RATIO * body_size


def split_run_in_headings(page: Page) -> int:
    """Promote a bold or larger FIRST LINE out of a prose block. Returns splits.

    Without this the classifier cannot see most of a textbook's headings, and
    the breadcrumb -- the whole reason a chunk about "ये मृदाएँ" can be found
    by someone asking about "काली मृदा" -- carries the wrong topic.

    NCERT sets its sub-headings run-in: same point size as the body, bold, and
    PyMuPDF returns them as line 0 of the paragraph that follows rather than
    as a block of their own:

        block, 8 lines, content_type=paragraph
          line0  size=14.0  bold=True   'काली मृदा'
          line1  size=14.0  bold=False  'इन मृदाओं का रंग काला है और इन्हे ...'

    `classify` judges a BLOCK: `is_bold` requires every span bold and
    `max_size` equals the body size here, so the block is prose and the
    heading inside it is invisible. Measured on the Class 10 Geography book
    before this pass: 54 distinct sections across 112 pages, with one stale
    heading ('चट्टानें') stamped on 12 consecutive chunks and 'काली मृदा'
    never appearing as a section at all -- so the passage naming the states
    where black soil is found had no way to be retrieved by a question that
    names the soil.
    """
    splits = 0
    rebuilt: list[Block] = []

    for block in page.blocks:
        if block.kind != "text" or len(block.lines) < 2:
            rebuilt.append(block)
            continue

        first, rest = block.lines[0], block.lines[1:]
        if not _is_run_in_heading(first, rest):
            rebuilt.append(block)
            continue

        for lines in ([first], rest):
            text = "\n".join(line.text for line in lines if line.text.strip())
            if not text.strip():
                continue
            rebuilt.append(
                Block(
                    index=block.index,
                    kind="text",
                    bbox=(
                        min(line.bbox[0] for line in lines),
                        min(line.bbox[1] for line in lines),
                        max(line.bbox[2] for line in lines),
                        max(line.bbox[3] for line in lines),
                    ),
                    lines=list(lines),
                    text=text,
                )
            )
        splits += 1

    if splits:
        for index, block in enumerate(rebuilt):
            block.index = index
        page.blocks = rebuilt
    return splits


def analyze_layout(page: Page) -> None:
    """Run column detection, block splitting and reading order on a page.

    The gutter is found once and reused: `find_gutter` is the expensive part
    (a 200-bin projection over every line on the page), and calling it again
    inside `assign_columns` would also risk the two disagreeing, since the
    split between them changes the boxes the second call would measure.
    """
    gutter_x = find_gutter(page)
    if gutter_x is not None:
        split_blocks_at_gutter(page, gutter_x)
    # After the gutter split, because that pass regroups a column's lines into
    # paragraphs and a run-in heading is the first line of one of them.
    split_run_in_headings(page)
    assign_columns(page, gutter_x)
    order_blocks(page)
