"""
Mathematical normalization.

A PDF does not record that r has an exponent. It records a small
glyph positioned slightly above and to the right of a larger one.
Join the text in reading order and the relationship is gone:

    r squared            ->  "r 2"
    epsilon-nought       ->  "e 0"
    Q over 4-pi-eps-0-r  ->  "0 ( ) 4 Q V r r e = p"

The geometry that encodes those relationships survives extraction --
font size, baseline offset, and the vector rules a fraction bar is
drawn with. This module reads it back out before the text is
flattened, and writes the relationship down in a form that
survives embedding.

WHAT IS RECOVERED

  superscripts   r^2, 10^-9      from font size + raised baseline
  subscripts     eps_0, r_1      from font size + lowered baseline
  fractions      (Q)/(4 pi r)    from a horizontal rule with spans
                                 above and below it

WHAT IS NOT

Integrals with limits, nested radicals, matrices and multi-line
derivations. Those need a structural parse, not a geometric one --
a maths-aware OCR over the equation's bounding box. The chunker
drops what comes out unreadable rather than letting it contaminate
the surrounding prose.

WHY CARET NOTATION rather than Unicode superscripts: it is what a
student types, it covers every character rather than the handful
Unicode has superscript forms for, and it survives tokenization as
something an embedding can use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A script glyph is markedly smaller than the text it attaches to.
MAX_SCRIPT_SIZE_RATIO = 0.85

# ...and its baseline is shifted by at least this share of the
# dominant font size. Rules out a line that merely mixes two sizes.
MIN_BASELINE_SHIFT_RATIO = 0.12

# A fraction bar is a filled rule: effectively zero height, and wide
# enough not to be a stray mark or a minus sign.
MAX_RULE_HEIGHT = 1.2
MIN_RULE_WIDTH = 8.0

# A span counts as part of a fraction only if it sits within this
# much of the rule's horizontal extent.
RULE_X_TOLERANCE = 2.0

# ...and close to it vertically. Measured against the span's own
# height, not the bar's width: a wide bar does not reach further up
# the page than a narrow one, and scaling by width let a 30pt bar
# swallow the prose two lines above it.
MAX_SCRIPT_GAP_LINES = 1.6

# A numerator is an expression, not a sentence. Three or more real
# words means the region caught running text, and the bar was a
# rule or an underline rather than a fraction.
MAX_WORDS_IN_PART = 2


@dataclass(frozen=True)
class Rule:
    """A horizontal line on the page: possibly a fraction bar."""

    x0: float
    y: float
    x1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    def covers(self, span_x0: float, span_x1: float) -> bool:
        return (
            span_x1 > self.x0 - RULE_X_TOLERANCE
            and span_x0 < self.x1 + RULE_X_TOLERANCE
        )

    def reaches(self, span_y: float, span_height: float) -> bool:
        gap = max(span_height, 6.0) * MAX_SCRIPT_GAP_LINES
        return abs(span_y - self.y) <= gap


def find_rules(page) -> list[Rule]:
    """
    Horizontal rules on a PyMuPDF page, candidates for fraction bars.

    Table borders and underlines land here too. They are filtered
    out later by requiring spans both above *and* below.
    """
    rules: list[Rule] = []

    try:
        drawings = page.get_drawings()
    except Exception:
        # A malformed content stream should cost us the equations on
        # this page, not the page itself.
        return rules

    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None:
            continue
        if rect.height <= MAX_RULE_HEIGHT and rect.width >= MIN_RULE_WIDTH:
            rules.append(Rule(x0=rect.x0, y=(rect.y0 + rect.y1) / 2, x1=rect.x1))

    return rules


def mark_scripts(spans: list[dict]) -> list[tuple[dict, str]]:
    """
    Label each span `base`, `super` or `sub` from its geometry.

    Returns pairs so the caller keeps the original span objects.
    """
    visible = [span for span in spans if span.get("text", "").strip()]
    if len(visible) < 2:
        return [(span, "base") for span in spans]

    dominant = max(span["size"] for span in visible)

    # The baseline of the full-size text on this line.
    baselines = [
        span["bbox"][3]
        for span in visible
        if span["size"] > dominant * MAX_SCRIPT_SIZE_RATIO
    ]
    if not baselines:
        return [(span, "base") for span in spans]

    baseline = max(set(baselines), key=baselines.count)
    threshold = dominant * MIN_BASELINE_SHIFT_RATIO

    marked: list[tuple[dict, str]] = []
    for span in spans:
        if not span.get("text", "").strip():
            marked.append((span, "base"))
            continue

        if span["size"] > dominant * MAX_SCRIPT_SIZE_RATIO:
            marked.append((span, "base"))
            continue

        shift = span["bbox"][3] - baseline
        if shift < -threshold:
            marked.append((span, "super"))
        elif shift > threshold:
            marked.append((span, "sub"))
        else:
            marked.append((span, "base"))

    return marked


def render_line(spans: list[dict]) -> str:
    """
    Flatten one line's spans, writing scripts as ^ and _.

    Runs of the same kind are grouped, so "10" as an exponent
    becomes 10^10 rather than 10^1^0.
    """
    marked = mark_scripts(spans)

    out: list[str] = []
    current = "base"
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        body = "".join(buffer).strip()
        if not body:
            buffer.clear()
            return
        if current == "super":
            out.append(f"^{body}" if len(body) == 1 else f"^({body})")
        elif current == "sub":
            out.append(f"_{body}" if len(body) == 1 else f"_({body})")
        else:
            out.append(body if not out else body)
        buffer.clear()

    for span, kind in marked:
        text = span.get("text", "")
        if kind != current:
            flush()
            current = kind
        buffer.append(text)
    flush()

    # Base runs keep the spacing the PDF had; scripts attach tight.
    rendered = ""
    for index, piece in enumerate(out):
        if index and not piece.startswith(("^", "_")):
            rendered += " "
        rendered += piece

    return rendered.strip()


def _span_centre(span: dict) -> tuple[float, float]:
    x0, y0, x1, y1 = span["bbox"]
    return (x0 + x1) / 2, (y0 + y1) / 2


def reconstruct_fractions(spans: list[dict], rules: list[Rule]) -> str | None:
    """
    Rebuild `numerator / denominator` around a horizontal rule.

    Returns None when no rule on this line has content both above
    and below it -- which is the common case, and the reason table
    borders and underlines do not produce spurious fractions.
    """
    visible = [span for span in spans if span.get("text", "").strip()]
    if not visible or not rules:
        return None

    for rule in rules:
        above: list[dict] = []
        below: list[dict] = []
        outside: list[dict] = []

        for span in visible:
            centre_x, centre_y = _span_centre(span)
            if not rule.covers(span["bbox"][0], span["bbox"][2]):
                outside.append(span)
            elif not rule.reaches(centre_y, span["bbox"][3] - span["bbox"][1]):
                outside.append(span)
            elif centre_y < rule.y:
                above.append(span)
            else:
                below.append(span)

        if not above or not below:
            continue

        numerator = render_line(sorted(above, key=lambda s: s["bbox"][0]))
        denominator = render_line(sorted(below, key=lambda s: s["bbox"][0]))
        if not numerator or not denominator:
            continue

        fraction = f"({numerator})/({denominator})"

        if outside:
            rest = render_line(sorted(outside, key=lambda s: s["bbox"][0]))
            # Whatever sat left of the bar leads; the rest follows.
            left = [s for s in outside if _span_centre(s)[0] < rule.x0]
            if left and len(left) != len(outside):
                lead = render_line(sorted(left, key=lambda s: s["bbox"][0]))
                tail_spans = [s for s in outside if s not in left]
                tail = render_line(sorted(tail_spans, key=lambda s: s["bbox"][0]))
                return " ".join(part for part in (lead, fraction, tail) if part)
            return f"{rest} {fraction}".strip() if left else f"{fraction} {rest}".strip()

        return fraction

    return None


# --- page-level assembly ---------------------------------------------
#
# PyMuPDF hands back a displayed equation as one block per glyph: the
# numerator, the denominator and every loose symbol arrive separately,
# ordered by position. Neither a per-line nor a per-block pass can see
# both sides of a fraction bar, so the bar has to be matched against
# every span on the page.

# A fraction bar is short. A table border or a section rule runs
# across the column, so width alone separates them.
MAX_BAR_WIDTH_RATIO = 0.25

# An equation region is a handful of glyphs, not a paragraph.
MAX_REGION_SPANS = 40


_WORD = re.compile(r"[A-Za-z\u0900-\u097F]{3,}")


def _is_expression(text: str) -> bool:
    """True when the text reads as maths rather than a sentence."""
    return len(_WORD.findall(text)) <= MAX_WORDS_IN_PART


@dataclass
class Fragment:
    """One span with the block it came from."""

    block: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float

    @property
    def centre_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def centre_y(self) -> float:
        return (self.y0 + self.y1) / 2


def _as_dict(fragment: Fragment) -> dict:
    """Shape a Fragment back into what render_line expects."""
    return {
        "text": fragment.text,
        "size": fragment.size,
        "bbox": (fragment.x0, fragment.y0, fragment.x1, fragment.y1),
    }


def assemble_fractions(
    fragments: list[Fragment],
    rules: list[Rule],
    page_width: float,
) -> list[tuple[set[int], str, tuple[float, float, float, float]]]:
    """
    Group page fragments into fractions around their bars.

    Returns one entry per fraction: the block indices it consumed,
    the reconstructed text, and its bounding box. Blocks not named
    in any entry are left exactly as they were.
    """
    results: list[tuple[set[int], str, tuple[float, float, float, float]]] = []
    claimed: set[int] = set()

    bars = [
        rule for rule in rules
        if rule.width <= page_width * MAX_BAR_WIDTH_RATIO
    ]

    for bar in sorted(bars, key=lambda r: (r.y, r.x0)):
        above: list[Fragment] = []
        below: list[Fragment] = []

        for fragment in fragments:
            if fragment.block in claimed:
                continue
            if not bar.covers(fragment.x0, fragment.x1):
                continue
            if not bar.reaches(fragment.centre_y, fragment.y1 - fragment.y0):
                continue
            (above if fragment.centre_y < bar.y else below).append(fragment)

        if not above or not below:
            continue
        if len(above) + len(below) > MAX_REGION_SPANS:
            continue

        numerator = render_line([_as_dict(f) for f in sorted(above, key=lambda f: f.x0)])
        denominator = render_line([_as_dict(f) for f in sorted(below, key=lambda f: f.x0)])
        if not numerator or not denominator:
            continue

        # Running text either side means this rule was not a
        # fraction bar. Leaving the blocks alone loses nothing;
        # inventing a fraction from a sentence corrupts the page.
        if not (_is_expression(numerator) and _is_expression(denominator)):
            continue

        used = above + below
        blocks = {fragment.block for fragment in used}
        claimed |= blocks

        box = (
            min(f.x0 for f in used),
            min(f.y0 for f in used),
            max(f.x1 for f in used),
            max(f.y1 for f in used),
        )
        results.append((blocks, f"({numerator})/({denominator})", box))

    return results
