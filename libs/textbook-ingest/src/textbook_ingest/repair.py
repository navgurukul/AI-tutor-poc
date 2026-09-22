"""S2 -- undo what the extractor did to the words.

Four defects, all measured across the eight-book corpus, none of them visible to
any rule downstream because they corrupt the tokens those rules match on.

1. THE SPACE IS A GLYPH.  Class 1 Math-Magic prints U+25A1 where a space
   belongs, so "May I put my" arrives as "May?I?put?my". Detected in fidelity,
   substituted here.

2. WORDS BROKEN BY A STRAY SPACE.  1.0 per 1,000 words on the MSCERT book, 16.1
   on NCERT Class 9 Science, clustering on kerned pairs: "natur e", "pr evious",
   "unifor m", "of f". Each one produces two tokens that are not words, which
   degrades the embedding and defeats any later phrase check -- the groundedness
   harness looks for answer phrases as substrings, and "natur e of this" will
   never match "nature of this".

3. DROP CAPS LOSE THEIR LETTER.  "uestions" appears seven times in Class 9
   Science: the Q is set as a decorative initial and extracts separately, or not
   at all.

4. DISPLAY TYPE EXTRACTS ONCE PER LAYER.  A shadowed heading comes back as
   "12.5 FA 12.5 FA12.5 FA CTORS ON WHICH THE RESISTCTORS ON WHICH THE RESIST",
   and "KEYWORDS KEYWORDS KEYWORDS KEYWORDS KEYWORDS". These are short,
   capitalised and punctuation-free, which is exactly the shape heading
   detection accepts, so they become topic labels.

EVERY RULE IS CONSERVATIVE. A join only happens when the book's own vocabulary
proves the joined form is a word it uses and the fragment is not. Deleting or
mangling a real word is the one mistake no later stage can undo, so where the
evidence is thin the text is left exactly as it came.
"""

import re
import unicodedata
from itertools import groupby
from typing import Dict, List, Optional

# Typographic characters pypdf hands back verbatim. NFKC folds the ligatures,
# but not these, and a chunk with a curly apostrophe tokenises differently from
# one with a straight apostrophe.
_PUNCTUATION = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
    "​": "", "﻿": "", "­": "",
}

# Real English words of one or two letters. A fragment that is one of these is
# a word in its own right, so "can be" and "in formation" are left alone.
_REAL_SHORT = frozenset(
    "a i an as at be by do go he if in is it me my no of on or so to up us we "
    "am ax ox ah oh hi id re ye lo".split()
)
# How often the joined form must appear in this book before a join is believed.
_JOIN_EVIDENCE = 3

# Any two words separated by exactly one space, on the same line. The split can
# fall anywhere -- "natur e", "pr evious", "exter nal", "envir onment" -- so the
# fragments are NOT length-limited, and the guard is frequency instead.
_SPLIT_PAIR = re.compile(r"\b([^\W\d_]+)[ ]([^\W\d_]+)\b", re.UNICODE)
# A join longer than this is more likely a coincidence than a repair.
_MAX_JOIN_CHARS = 22
# A run of isolated single letters this long is figure debris, not text.
# Three, because that is the length the debris actually comes in: NCERT Class 6
# yields "ca t t A", "m e t", "s t n e". English prose does not put three
# single-letter tokens in a row -- exercise options carry brackets, "(a) (b)" --
# and the run is only dropped after failing to resolve forwards or backwards.
_UNREADABLE_RUN = 3
# Three or more single letters spaced apart: vertical figure text, often reversed.
_LETTER_RUN = re.compile(r"(?:(?<=\s)|^)((?:[^\W\d_]\s){2,}[^\W\d_])(?=\s|$)", re.UNICODE)


def normalise_characters(text: str, space_substitute: Optional[str] = None) -> str:
    """Fold typographic characters down to plain text.

    NFKC turns the fi/fl ligatures textbooks are full of back into real letters,
    which matters because "flower" spelled with a ligature is a different token
    to the embedding model and only one of the two is a word.
    """
    if space_substitute:
        text = text.replace(space_substitute, " ")
    for source, target in _PUNCTUATION.items():
        text = text.replace(source, target)
    return unicodedata.normalize("NFKC", text)


def _known(vocab: Dict[str, int], word: str, floor: int = _JOIN_EVIDENCE) -> bool:
    return vocab.get(word.lower(), 0) >= floor


def should_join(w1: str, w2: str, vocab: Dict[str, int]) -> bool:
    """Whether "w1 w2" is one word the extractor broke in half.

    The book is its own dictionary, and the counts are taken from the UNREPAIRED
    text, which is what makes this work: a word that is sometimes split and
    sometimes not leaves both forms behind, and the whole form is the commoner
    one. Measured over NCERT Class 9 Science --

        external 14   vs  exter 7 / nal 9
        large    36   vs  lar  13 / ge  13
        previous  6   vs  pr  158 / evious 3

    -- so the test is that the joined form is one the book really uses, and is
    at least as common as the RARER of the two fragments. That second clause is
    what protects genuine word pairs: "some what" would need "somewhat" to be as
    common as "some", and it never is.

    Two-letter English words are excluded outright, which covers the dangerous
    family -- "in formation", "of ten", "to get her", "the rapist" -- without
    needing a dictionary.
    """
    a, b = w1.lower(), w2.lower()
    if a in _REAL_SHORT or b in _REAL_SHORT:
        return False
    if len(a) + len(b) > _MAX_JOIN_CHARS:
        return False
    joined = vocab.get(a + b, 0)
    if joined < _JOIN_EVIDENCE:
        return False
    return joined >= min(vocab.get(a, 0), vocab.get(b, 0))


def repair_splits(text: str, vocab: Dict[str, int]) -> str:
    """Rejoin words a stray space broke in half.

    Walks the tokens of each line rather than substituting on a regex. A regex
    consumes both words of a pair, so in "the exter nal envir onment" it would
    test "the exter", reject it, and resume past "exter" -- missing "exter nal"
    entirely. Walking the tokens lets every adjacent pair be considered.

    Repeated until stable, because a word can be broken more than once: Class 9
    Science yields "st ructur e" for "structure".
    """
    lines = text.split("\n")
    out: List[str] = []
    for line in lines:
        for _ in range(3):
            tokens = line.split(" ")
            merged: List[str] = []
            i = 0
            changed = False
            while i < len(tokens):
                if i + 1 < len(tokens):
                    a, b = tokens[i], tokens[i + 1]
                    if a.isalpha() and b.isalpha() and should_join(a, b, vocab):
                        merged.append(a + b)
                        i += 2
                        changed = True
                        continue
                merged.append(tokens[i])
                i += 1
            line = " ".join(merged)
            if not changed:
                break
        out.append(line)
    return "\n".join(out)


def repair_dropped_initials(text: str, vocab: Dict[str, int]) -> str:
    """Rejoin a drop cap to the word it was set apart from.

    A decorative initial is a separate text object, so it extracts onto its own
    line: Class 9 Science yields a line "Q" followed by a line "uestions",
    seven times over, and both halves then look like recurring section labels.

    This is deliberately a LINE-level rule, not a word-level one. The obvious
    word-level version -- for any token, try prepending each letter and take
    whichever makes a word the book uses -- is unsafe in a way that is easy to
    miss: "here" would become "there" and "our" would become "four" wherever the
    longer word happened to be commoner. Requiring the initial to actually be
    sitting alone on the preceding line removes the guesswork entirely.
    """
    lines = text.split("\n")
    out: List[str] = []
    skip = False
    for i, line in enumerate(lines):
        if skip:
            skip = False
            continue
        stripped = line.strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if (
            len(stripped) == 1
            and stripped.isalpha()
            and stripped.isupper()
            and nxt[:1].islower()
        ):
            head = re.match(r"^[^\W\d_]+", nxt, re.UNICODE)
            if head and _known(vocab, stripped + head.group(0), 2):
                out.append(stripped + nxt)
                skip = True
                continue
        out.append(line)
    return "\n".join(out)


def collapse_repeats(text: str) -> str:
    """Collapse display type that extracted once per layer.

    Two shapes: whole tokens repeated in a row ("KEYWORDS KEYWORDS KEYWORDS"),
    and one string concatenated to itself with no separator
    ("SpeakingSpeakingSpeaking"). Three occurrences is the floor -- English
    genuinely repeats a word twice ("very very"), never three times in a row.
    """
    # token-level: a run of three or more identical tokens becomes one. Two is
    # left alone, because English does repeat a word twice ("very very").
    out = []
    for line in text.split("\n"):
        kept: List[str] = []
        for token, group in groupby(line.split(" ")):
            run = list(group)
            kept.extend([token] if token and len(run) >= 3 else run)
        out.append(" ".join(kept))
    text = "\n".join(out)

    # character-level: a token that is one string repeated 3+ times
    def unrepeat(match: "re.Match") -> str:
        word = match.group(0)
        n = len(word)
        for period in range(1, n // 3 + 1):
            if n % period:
                continue
            unit = word[:period]
            if unit * (n // period) == word and n // period >= 3:
                return unit
        return word

    return re.sub(r"[^\W\d_]{6,}", unrepeat, text, flags=re.UNICODE)


def repair_letter_runs(text: str, vocab: Dict[str, int]) -> str:
    """Rebuild vertical figure text that extracted one letter at a time.

    NCERT Class 6 yields "table e h t d" on a figure -- "e h t" is "the"
    backwards. Only rewritten when the joined run, forwards or reversed, is a
    word this book uses; otherwise it is left for the debris filters, because
    guessing at a run of loose letters invents text.
    """

    def fix(match: "re.Match") -> str:
        run = match.group(1)
        letters = [c for c in run.split(" ") if c]
        joined = "".join(letters)
        if _known(vocab, joined, 2):
            return joined
        reversed_ = "".join(reversed(letters))
        if _known(vocab, reversed_, 2):
            return reversed_
        # Unrecoverable. A run of this many isolated single letters is a figure
        # axis or a rotated label, never prose -- NCERT Class 6 is full of them
        # ("ca t t A", "s t n e", "e e h g") -- so it is dropped rather than
        # left to pollute a chunk. Shorter runs are kept, because "a b c" can
        # legitimately appear in a list.
        if len(letters) >= _UNREADABLE_RUN:
            return " "
        return match.group(0)

    return _LETTER_RUN.sub(fix, text)


def repair_page(text: str, vocab: Dict[str, int], space_substitute: Optional[str] = None) -> str:
    """The whole repair pass for one page, in the order the defects nest."""
    text = normalise_characters(text, space_substitute)
    text = collapse_repeats(text)
    text = repair_letter_runs(text, vocab)
    text = repair_splits(text, vocab)
    text = repair_dropped_initials(text, vocab)
    return text
