"""S4 -- remove the furniture the profile found, including where it is fused.

Dropping whole lines is not enough. On NCERT Class 10 Science p.206 extraction
glues the running header to the first words of the body:

    Science206 that motion of electrons in an electric circuit constitutes an
    electric current...

The header is not on a line of its own, so any rule that deletes lines either
misses it or deletes a sentence. What makes the fused case safe to strip is the
page number: a real sentence opening with the same word ("Science is the study
of...") has no digits after it, so requiring digits between the template and the
rest of the line separates the two cleanly.
"""

import re
from typing import List, Sequence, Set

# A line that is only a page number, however decorated: "87", "- 87 -", "|87|".
_PAGE_NUMBER = re.compile(r"^[\s|\-–—_.]*\d{1,4}[\s|\-–—_.]*$")
# An edition marker on its own line. Covers NCERT's bare "2020-21", the
# "Reprint 2025-26" of older printings, and "Rationalised 2023-24".
_EDITION = re.compile(
    r"^\s*(?:reprint(?:ed)?|rationalised|rationalized)?\s*"
    r"\d{4}\s*[-–]\s*\d{2,4}\s*$",
    re.IGNORECASE,
)
# A line with almost no letters: a rule, a border, extraction debris off a
# diagram. Three or more characters so a lone bullet is not swept up here.
_MOSTLY_SYMBOLS = re.compile(r"^[^A-Za-z0-9]{3,}$")
# What has to sit between a fused header and the body for the strip to be safe.
_FUSED = r"\s*\d{1,4}\s*"
# Below this the remainder is not a sentence worth rescuing, so drop the line.
_MIN_REMAINDER = 12


def _fused_prefix(line: str, furniture: Sequence[str]) -> str:
    """Strip a leading furniture template plus its page number, if present.

    Returns the line unchanged when there is no fused header. Longest template
    first, so "THE FUNDAMENTAL UNIT OF LIFE" wins over a shorter one that
    happens to be a prefix of it.
    """
    for tpl in sorted(furniture, key=len, reverse=True):
        if len(tpl) < 3 or not line.startswith(tpl):
            continue
        rest = line[len(tpl):]
        match = re.match(_FUSED, rest)
        if not match or not match.group(0).strip():
            continue                      # no page number: an ordinary sentence
        remainder = rest[match.end():].strip()
        if len(remainder) >= _MIN_REMAINDER:
            return remainder
        return ""                          # header and nothing else
    return line


def strip_page(page: str, furniture: Set[str]) -> str:
    """One page with its furniture removed, blank lines preserved.

    Blank lines are kept because reflow uses them as paragraph separators; only
    the furniture itself goes.
    """
    kept: List[str] = []
    for raw in page.splitlines():
        line = raw.strip()
        if not line:
            kept.append("")
            continue
        from .profile import template

        if template(line) in furniture:
            continue
        if _PAGE_NUMBER.match(line):
            continue
        if _EDITION.match(line):
            continue
        if _MOSTLY_SYMBOLS.match(line):
            continue

        rescued = _fused_prefix(line, furniture)
        if not rescued:
            continue
        kept.append(rescued)
    return "\n".join(kept)


def strip_pages(pages: Sequence[str], furniture: Set[str]) -> List[str]:
    return [strip_page(page, furniture) for page in pages]
