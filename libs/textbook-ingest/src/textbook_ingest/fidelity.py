"""S1 -- decide whether the extracted text is usable at all.

The old `looks_like_scan` only summed characters, which misses every failure
where the extractor returns plenty of characters and none of them are letters.
Measured on NCERT Class 1 Math-Magic: 3,054 WHITE SQUARE characters standing in
for spaces, 1,612 raw glyph ids like `/B4f/B6e/B65` from fonts with no ToUnicode
map, 544 characters per page against 1,700-2,300 for every other book -- and
`looks_like_scan` returned False, so the book ingested into 147 chunks of noise.

Three verdicts, because they need different handling:

  ok        index it.
  repair    a mechanical defect the next stage can undo -- most importantly a
            font that renders the space as a visible glyph. Rejecting these
            would throw away a readable book.
  reject    nothing here is worth indexing, and the caller is given a reason
            the user can act on.

The thresholds are deliberately loose. A false "reject" loses a whole textbook;
a false "ok" costs some noisy chunks that the later filters still see.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set

# A font with no ToUnicode CMap: pypdf falls back to emitting glyph names.
# "/B4f/B6e/B65" is "One". Also seen as "/square6" for a bullet, which is a
# single leaked name rather than whole words, so the ratio matters, not presence.
GLYPH_NAME = re.compile(r"/[A-Za-z][A-Za-z0-9]{1,5}")
# Characters that turn up where a space belongs when the font maps 0x20 oddly.
SPACE_CANDIDATES = "□■▫▪�¤☐"
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

# Below this there is no text layer worth the name. Scales with page count so a
# short handout is not judged by a textbook's standard.
_SCAN_FLOOR = 200
# A page of a real textbook. Class 1 Math-Magic sits at 544 and is mostly
# pictures; the other seven books measured 1,349-2,320.
_THIN_PAGE_CHARS = 300
# Share of the extracted text that may be glyph names before it is unreadable.
_GLYPH_LIMIT = 0.02
# ...and how many DISTINCT names must be involved. A single repeated name is a
# bullet or a dingbat; a spread of them is text that was never mapped.
_GLYPH_VARIETY = 12
# A single glyph name taking this share of all hits is a dingbat -- a bullet or
# an arrow the font never mapped -- not evidence that the text is unreadable.
_DINGBAT_SHARE = 0.25
# How often a candidate must sit between two letters before it is a space.
_SPACE_EVIDENCE = 20


@dataclass
class FidelityReport:
    verdict: str = "ok"                       # ok | repair | reject
    reasons: List[str] = field(default_factory=list)
    hint: str = ""
    code: str = ""
    space_substitute: Optional[str] = None
    # Glyph names that are really bullets; the profile picks these up as such.
    dingbats: Set[str] = field(default_factory=set)
    stats: Dict[str, object] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.verdict != "reject"


def detect_space_substitute(text: str) -> Optional[str]:
    """The character this book prints where a space belongs, if any.

    Requires the character to actually sit between two letters, repeatedly --
    a book may legitimately contain a few geometric shapes, and a bullet at the
    start of a line is not a space.
    """
    best = None
    best_hits = 0
    for candidate in SPACE_CANDIDATES:
        if candidate not in text:
            continue
        hits = len(re.findall(
            "(?<=[^\\W\\d_]){}(?=[^\\W\\d_])".format(re.escape(candidate)), text, re.UNICODE
        ))
        if hits > best_hits:
            best, best_hits = candidate, hits
    return best if best_hits >= _SPACE_EVIDENCE else None


def assess(raw_pages: Sequence[str]) -> FidelityReport:
    """Judge the extracted text before anything is built on it."""
    report = FidelityReport()
    pages = list(raw_pages)
    if not pages:
        return FidelityReport(
            verdict="reject", code="empty",
            reasons=["no pages were extracted"],
            hint="Check the file is a PDF and is not empty.",
        )

    joined = "".join(pages)
    total = len(joined)
    per_page = sorted(len(p) for p in pages)
    median_page = per_page[len(per_page) // 2] if per_page else 0
    letters = len(_LETTER.findall(joined))
    glyphs = GLYPH_NAME.findall(joined)
    glyph_chars = sum(len(g) for g in glyphs)
    glyph_ratio = glyph_chars / total if total else 0.0

    report.stats = {
        "pages": len(pages),
        "chars": total,
        "median_chars_per_page": median_page,
        "letter_ratio": round(letters / total, 3) if total else 0.0,
        "glyph_name_tokens": len(glyphs),
        "glyph_ratio": round(glyph_ratio, 4),
    }

    # 1. No text layer at all -- a scan.
    if total < _SCAN_FLOOR * (len(pages) ** 0.5):
        return FidelityReport(
            verdict="reject", code="no_text_layer",
            reasons=["only {} characters across {} pages".format(total, len(pages))],
            hint="This looks like a scanned PDF. Run it through OCR to produce a "
                 "searchable PDF, then try again.",
            stats=report.stats,
        )

    # 2. Fonts with no Unicode mapping. Nothing downstream can recover this.
    #
    # Neither volume nor variety is the signal on its own, and each in turn
    # rejected a perfectly readable book. NCERT Class 5 EVS leaks "/rhombus"
    # because that is the glyph NAME of its bullet: 3% of the text, and 20
    # distinct names once the odd stray is counted. What separates it from a
    # genuinely unmapped font is CONCENTRATION -- one name is 97% of its hits,
    # while Class 1 Math-Magic's commonest is 9% of 84 names spelling out words.
    #
    # So a name that dominates is a dingbat, set aside as a bullet rather than
    # counted as corruption, and the ratio is recomputed on what is left.
    counts = Counter(glyphs)
    dingbats = {
        name for name, hits in counts.items()
        if hits >= len(glyphs) * _DINGBAT_SHARE
    }
    residual = [g for g in glyphs if g not in dingbats]
    residual_ratio = sum(len(g) for g in residual) / total if total else 0.0
    report.stats["distinct_glyph_names"] = len(counts)
    report.stats["dingbats"] = sorted(dingbats)
    report.stats["residual_glyph_ratio"] = round(residual_ratio, 4)
    report.dingbats = dingbats

    if residual_ratio > _GLYPH_LIMIT and len(set(residual)) >= _GLYPH_VARIETY:
        return FidelityReport(
            verdict="reject", code="unmapped_fonts",
            reasons=["{:.0%} of the text is raw glyph ids in {} distinct forms "
                     "(e.g. {})".format(
                         residual_ratio, len(set(residual)),
                         ", ".join(sorted(set(residual))[:3]))],
            hint="The PDF's fonts carry no Unicode mapping, so the text cannot be "
                 "read. Re-export the PDF with embedded font encodings, or OCR it.",
            stats=report.stats,
        )

    # 3. A visible glyph standing in for the space. Repairable, not fatal.
    substitute = detect_space_substitute(joined)
    if substitute:
        report.verdict = "repair"
        report.space_substitute = substitute
        report.reasons.append(
            "U+{:04X} {} is used as the space character".format(
                ord(substitute), unicodedata.name(substitute, "?"))
        )

    # 4. Thin pages. Worth saying, never worth refusing on its own -- a maths or
    #    picture book is legitimately sparse.
    if median_page < _THIN_PAGE_CHARS:
        report.reasons.append(
            "median {} characters per page; this book is mostly images".format(median_page)
        )
        report.stats["thin"] = True

    return report


def summarise_vocabulary(pages: Sequence[str]) -> Counter:
    """Word frequencies over the whole book.

    Used by the repair pass, which needs to know whether a proposed join
    produces a word this book actually uses. Built once and carried on the
    profile rather than recomputed per page.
    """
    counts: Counter = Counter()
    for page in pages:
        for word in re.findall(r"[^\W\d_]+", page.lower(), re.UNICODE):
            if len(word) > 1:
                counts[word] += 1
    return counts
