"""S6 -- what a line is: heading, caption, list item, table row or prose.

Heading detection decides two separate things, and it is worth being explicit
about both, because turning the breadcrumb off only removes one of them:

  * the label a chunk carries into its embedding, and
  * WHERE THE TEXT IS CUT, because a heading closes the current chunk.

So a false heading costs a wrong label and a broken chunk, and the second cost
is paid whether or not the label is ever embedded. Measured on NCERT Class 9
Science: 324 distinct headings over 17 chapters, 4.7 chunks per page against
2.8 on MSCERT. That fragmentation is what this module exists to stop.

The validation rejects four shapes that are not topics, each one measured:

  furniture     "SCIENCE64", "/ Beehive", "Looking Around" -- a running header,
                caught through the profile rather than by pattern.
  table rows    "Yes Yes None", "Points Solids Liquids Gases", "Group A Group B"
                -- a row or header of a table, flattened by extraction into
                something that looks exactly like a short title.
  fragments     "The British scientist Michael", "The support at which the rod
                of a lever is" -- prose that happens to start a line.
  apparatus     "3. Fill in the blanks with the appropriate", "5. Go toward the
                left" -- an exercise instruction or an activity step.
"""

import re
from typing import Optional, Sequence

from .types import BookProfile

_MAX_HEADING_CHARS = 90
_MAX_HEADING_WORDS = 12
# Punctuation that ends a sentence mid-prose. A question mark is deliberately
# absent: textbooks are full of headings like "Why do we fall ill?".
_SENTENCE_END = re.compile(r"[.,;:]$")
_ENDS_SENTENCE = re.compile(r"[.!?:;][\"')\]]*$")
_CONTINUATION = re.compile(r"^[a-z,;)\]]")
_NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S")
_FIGURE_NUMBER = re.compile(r"^\d+(?:\.\d+)*\s*[:.]\s*")
_LIST_NUMBER = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+")
_LETTERS = re.compile(r"[A-Za-z]")
# "28620C", "1000C", "70 GSM" -- extraction debris off a diagram or a colophon.
_MOSTLY_DIGITS = re.compile(r"^[\d\s.,:;/%()\-]*[A-Za-z]{0,2}[\d\s.,:;/%()\-]*$")

# No heading ends on one of these, and no sentence breaks off after one.
_DANGLING = frozenset(
    "a an and as at by for from in into is are of on or than that the their its "
    "his her him to which with was were be been has have had not but so if when "
    "while where who whose this these those".split()
)
# Function words. A run of Title-Case nouns with none of these, three or more
# long, is a table header rather than a section title -- "Points Solids Liquids
# Gases" against "Fun with Magnets".
_FUNCTION = frozenset(
    "a an the and or of in on at to for with from by as is are was were be into "
    "our its their his her this that these those we you they it".split()
)
# Cell values that only ever appear in a table.
_CELL_WORDS = frozenset("yes no none nil na true false".split())

# An imperative that opens an activity step rather than naming a topic.
_IMPERATIVE = re.compile(
    r"^(?:rub|take|hold|observe|spread|collect|write|draw|go\b|put|stir|fill|"
    r"choose|match|find|make|prepare|name|give|solve|complete|identify|classify|"
    r"read|visit|cut|place|keep|bring|tie|repeat|note|discuss|think|look|try|"
    r"measure|count|list|state|explain|describe|answer|select|arrange|fix|using|"
    r"switch|pour|drop|press|push|pull|move|tell|ask|compile|obtain|prove|show)\b",
    re.IGNORECASE,
)

_CAPTION_PREFIXED = re.compile(
    r"^(?:fig|figure|table|chart|photo|map|graph)s?\.?\s*\d+(?:\.\d+)*\s*[:.]?\s*",
    re.IGNORECASE,
)
_CAPTION_NUMERIC = re.compile(r"^\d+\.\d+\s*:\s*\S")

_ITEM_NUMBERED = re.compile(
    r"^(?:\d{1,2}\s*[.)]\s|\(\s*[a-z]{1,2}\s*\)|[a-z]\)\s|\(\s*[ivx]{1,4}\s*\))"
)


def is_caption(line: str, profile: Optional[BookProfile] = None) -> bool:
    """A figure or table caption, in whichever form this book uses.

    The old rule matched only "10.8 : Frictional force" and so matched nothing
    at all on NCERT, where captions read "Fig. 8.3: Distance-time graph...".
    511 such captions survived into the four NCERT science corpora.
    """
    text = line.strip()
    style = profile.caption_style if profile else "none"
    if style in ("prefixed", "none") and _CAPTION_PREFIXED.match(text):
        return True
    if style in ("numeric", "none") and _CAPTION_NUMERIC.match(text):
        return True
    return False


def is_item_start(line: str, profile: Optional[BookProfile] = None) -> bool:
    """Opens a list item, an exercise option or a bullet.

    The bullet token comes from the profile, because it is often not a bullet
    character: MSCERT's round bullet extracts as a lowercase L, NCERT Class 10's
    as the glyph name "/square6".
    """
    text = line.lstrip()
    if _ITEM_NUMBERED.match(text):
        return True
    bullets = profile.bullets if profile else set()
    for token in bullets:
        if text.startswith(token + " ") or text.startswith(token + "\t"):
            return True
    if text[:1] in "•●▪◦·":
        return True
    # MSCERT's bullet, only when followed by a capital: no English sentence
    # starts with a lone "l".
    return bool(re.match(r"^l\s+(?=[A-Z])", text))


def looks_like_display_garbage(line: str) -> bool:
    """Layered display type whose copies extraction interleaved.

    "12.5 FA 12.5 FA12.5 FA 12.5 FA12.5 FA CTORS ON WHICH THE RESISTCTORS ON
    WHICH THE RESIST" is the Class 10 Science heading "12.5 FACTORS ON WHICH
    THE RESISTANCE..." set with a shadow, extracted once per copy and woven
    together. Unlike the plain repeated case ("KEYWORDS KEYWORDS KEYWORDS"),
    the copies are not adjacent, so repair cannot reconstruct the original --
    and inventing one would be worse than leaving it.

    What it can do is stop the wreckage becoming a topic label, which is what
    happened before: the string is short, capitalised and has no sentence
    punctuation, which is exactly the shape heading detection accepts.
    """
    tokens = [t for t in line.split() if len(t) > 1]
    if len(tokens) < 4:
        return False
    counts = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return max(counts.values()) >= 3


def looks_like_table_row(line: str) -> bool:
    """A row or header of a table, flattened into one line by extraction."""
    text = " ".join(line.split())
    tokens = text.split()
    if len(tokens) < 2 or _ENDS_SENTENCE.search(text):
        return False
    lower = [w.lower().strip(".,:;()") for w in tokens]
    # Column letters ("Group A Group B") are labels, not English words, so they
    # are set aside before asking whether any function words are present.
    meaningful = [w for w in lower if len(w) > 1]
    has_function = any(w in _FUNCTION for w in meaningful)
    # A repeated token inside one short line is a column pattern -- but only
    # when nothing joins the words together. "Motion and Types of Motion" is a
    # real chapter heading that repeats a word; "Effort Fulcrum Effort" is a
    # figure's column labels. The function words are what separate the two.
    if len(tokens) <= 8 and not has_function and len(set(meaningful)) < len(meaningful):
        return True
    if all(w in _CELL_WORDS for w in lower):
        return True
    digits = sum(1 for w in tokens if any(c.isdigit() for c in w))
    if digits * 2 >= len(tokens):
        return True
    # Three or more Title-Case words and not one function word between them.
    if len(tokens) >= 3 and not any(w in _FUNCTION for w in lower):
        if all(w[:1].isupper() for w in tokens):
            return True
    return False


def looks_like_heading(line: str, profile: Optional[BookProfile] = None) -> bool:
    """True for a line shaped like a section heading rather than body text."""
    text = line.strip()
    if not text or len(text) > _MAX_HEADING_CHARS:
        return False
    if _SENTENCE_END.search(text):
        return False
    if text[:1].islower():
        return False
    if is_caption(text, profile):
        return False
    if looks_like_display_garbage(text):
        return False
    words = text.split()
    if words[-1].lower().strip(".,:;") in _DANGLING:
        return False
    if _NUMBERED_HEADING.match(text):
        return True
    if len(words) > _MAX_HEADING_WORDS:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    if all(c.isupper() for c in letters):
        return True
    capitalised = sum(1 for w in words if w[:1].isupper())
    return capitalised >= max(2, int(len(words) * 0.7))


def clean_heading(heading: str, profile: Optional[BookProfile] = None) -> str:
    """The heading worth keeping as a topic label, or "" for anything else.

    Returning "" is always safe: the caller falls back to no label. What is not
    safe is letting a running header or a table row through, because it then
    labels every chunk until the next heading.
    """
    from .profile import template

    text = " ".join((heading or "").split())
    if not text:
        return ""

    # The syllabus table numbers sections "06.72.01", so one pass leaves
    # "01 Identifies materials..." behind.
    for _ in range(3):
        stripped = _FIGURE_NUMBER.sub("", text, count=1)
        if stripped == text:
            stripped = _LIST_NUMBER.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    text = text.strip(" .:;-–—")
    if not text:
        return ""

    if profile:
        if template(text) in profile.furniture:
            return ""
        if text in profile.labels:
            return ""
    if _MOSTLY_DIGITS.match(text):
        return ""
    if len(_LETTERS.findall(text)) < 4:
        return ""
    if "?" in text:
        return ""
    if looks_like_table_row(text) or looks_like_display_garbage(text):
        return ""
    if _IMPERATIVE.match(text):
        return ""
    words = text.split()
    if len(words) > 8:
        return ""
    if words[-1].lower() in _DANGLING:
        return ""
    if _is_sentence_case(words):
        return ""
    return text


def _is_sentence_case(words: Sequence[str]) -> bool:
    """A phrase set in sentence case rather than title case, so: prose.

    "The British scientist Michael" labelled eight chunks of the MSCERT corpus.
    It is the opening of "The British scientist Michael Faraday discovered...",
    left behind when reflow declined to join the line. The tell is "scientist":
    a title-cased heading capitalises its content words and lowercases only
    function words, so a lowercase CONTENT word means this was never a title.

    Deliberately applied only to the label. A heading still closes a chunk even
    when it is rejected here, so over-rejecting costs a missing breadcrumb --
    which is off by default -- and never a merged section.
    """
    if len(words) < 3:
        return False
    letters = [c for w in words for c in w if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return False                      # ALL CAPS is a heading convention
    for word in words[1:]:
        bare = word.strip(".,:;()'\"").lower()
        if not bare or not bare.isalpha():
            continue
        if bare in _FUNCTION or bare in _DANGLING:
            continue
        if word[:1].islower():
            return True
    return False


def opens_body(text: str, long_enough: float) -> bool:
    """What a heading has to be followed by: prose, or a list of steps.

    A table's header row is as Title-Case as any heading. What follows one is a
    column of cells, which neither ends a sentence nor runs the width of the
    column.
    """
    return bool(
        _ENDS_SENTENCE.search(text)
        or len(text) >= long_enough
        or _ITEM_NUMBERED.match(text)
    )


_BODY_PARAGRAPH_CHARS = 80


def is_section_heading(
    paragraphs: Sequence[str], index: int, profile: Optional[BookProfile] = None
) -> bool:
    """`paragraphs[index]` opens a section: heading-shaped, and followed by body.

    A heading followed by another heading qualifies if that one does -- a
    chapter title sitting directly above its first section.
    """
    for i in range(index, len(paragraphs)):
        if not looks_like_heading(paragraphs[i], profile):
            return i > index and opens_body(paragraphs[i], _BODY_PARAGRAPH_CHARS)
        if i + 1 >= len(paragraphs):
            return True
    return False
