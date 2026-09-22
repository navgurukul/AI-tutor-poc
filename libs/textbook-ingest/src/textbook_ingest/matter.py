"""Front and back matter: the pages that are not the book.

Measured on the shipped MSCERT corpus: 33 of 373 chunks (9%) came from the
title page, the publication credits, the contents listing, the learning-outcomes
tables and the Marathi glossary. None of them can answer a science question and
all of them are searchable. The worst is the glossary, which produced the two
largest chunks in the corpus -- 1,765 and 1,382 characters -- because it has no
sentence punctuation for the long-paragraph splitter to divide on, so if it is
ever retrieved it consumes the whole prompt budget by itself. Its breadcrumb
was "Group A Group B".

This module deletes pages, which is the dangerous direction: a page wrongly
dropped takes facts with it and no later stage can put them back. So every rule
here is bounded twice -- by evidence, and by how much of the book it is allowed
to remove -- and everything it removes is reported to the caller.
"""

import re
from typing import List, Optional, Sequence, Tuple

from .types import Warning_

# Front matter may not run past this share of the book. A textbook with 40% of
# its pages before page 1 is not a textbook, and the page numbering has been
# misread.
_MAX_FRONT = 0.20
# Back matter likewise. A glossary and an index are a few pages, not a chapter.
_MAX_BACK = 0.12
# Printed numbers must be found on at least this share of pages before they are
# trusted to locate the body.
_MIN_NUMBERED = 0.40
# A page this impure is not written in the book's own script.
_FOREIGN_RATIO = 0.20
# "amphibian - उभयचर", "boiling point - उत्कलनांक": a glossary line.
_GLOSSARY_LINE = re.compile(r"^[^\n]{2,40}\s[-–:]\s\S")
_LATIN = re.compile(r"[A-Za-z]")
_SCRIPT = re.compile(r"[^\W\d_]", re.UNICODE)


def _foreign_ratio(text: str) -> float:
    """Share of the page's letters that are not Latin."""
    letters = _SCRIPT.findall(text)
    if not letters:
        return 0.0
    latin = sum(1 for c in letters if _LATIN.match(c))
    return 1.0 - (latin / len(letters))


def _is_reference_page(text: str) -> bool:
    """A glossary or index page: a column of short term-definition lines."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 5:
        return False
    entries = sum(1 for l in lines if _GLOSSARY_LINE.match(l))
    sentences = sum(1 for l in lines if re.search(r"[.!?]\s", l))
    return entries >= len(lines) * 0.5 and sentences <= len(lines) * 0.2


def find_body(
    pages: Sequence[str], numbers: Sequence[Optional[int]]
) -> Tuple[int, int, List[Warning_]]:
    """The half-open range of pages that are the book itself.

    Front matter is located by the printed page numbering, which is the only
    signal that generalises: a textbook's body starts where printed page 1 is,
    whatever sits before it. Back matter is located by content, because a
    glossary carries page numbers like any other page.
    """
    warnings: List[Warning_] = []
    total = len(pages)
    start, end = 0, total
    if total < 10:
        return start, end, warnings

    numbered = sum(1 for n in numbers if n)
    if numbered >= total * _MIN_NUMBERED:
        for index, number in enumerate(numbers):
            if number == 1:
                if 0 < index <= total * _MAX_FRONT:
                    start = index
                    warnings.append(Warning_(
                        "front_matter_dropped",
                        "{} pages before printed page 1 (cover, credits, contents)".format(index),
                    ))
                break

    dropped_back = 0
    limit = int(total * _MAX_BACK)
    for index in range(total - 1, start, -1):
        if dropped_back >= limit:
            break
        text = pages[index]
        if not text.strip():
            dropped_back += 1
            continue
        if _foreign_ratio(text) >= _FOREIGN_RATIO or _is_reference_page(text):
            dropped_back += 1
            continue
        break
    if dropped_back:
        end = total - dropped_back
        warnings.append(Warning_(
            "back_matter_dropped",
            "{} trailing pages (glossary or index)".format(dropped_back),
        ))

    return start, end, warnings
