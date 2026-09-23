"""Repairing Devanagari that a PDF's own font map got wrong.

Not legacy-font conversion -- that is `legacy_hindi`, and it fires on a font
NAME. This module handles the subtler failure: a perfectly ordinary Unicode
font whose ToUnicode table maps some glyphs to the wrong code points, so the
text extracts as valid, well-formed, confidently wrong Devanagari.

That is the worst shape a bug can take here. The script is right, the length is
right, it embeds without complaint, and the only symptom is that a question
about ऊर्जा never finds the chapter on ऊर्जा -- which is indistinguishable, from
the outside, from the model just being bad at Hindi.

Both repairs below were measured on the Class X NCERT Geography book
(समकालीन भारत-2) in the live library on 2026-09-20.
"""

import re
from typing import List, Tuple

# -- the फ family ----------------------------------------------------------
#
# 36 chunks, 49 occurrences, 59 distinct damaged word forms. The font draws फ
# from pieces, and the pieces map to their own code points rather than to फ,
# so the letter arrives as a small cluster of unrelated ones. Three shapes:
#
#   प़्ा  before फ   spurious prefix     कार्टोग्राप़्ाफी -> कार्टोग्राफी
#   व्र   before फ   wrong base letter   व्रिफयाकलाप     -> क्रियाकलाप
#   उ     before फ   wrong vowel         उफर्जा          -> ऊर्जा
#
# This damaged CHAPTER TITLES, which is what makes it worth a table rather
# than a shrug: "खनिज तथा उफर्जा संसाधन" is the energy-resources chapter, and
# its own heading did not contain the word a student would search for. The
# heading is also the breadcrumb every chunk beneath it is embedded with, so
# one broken title degrades a whole chapter's retrieval, not one passage.
#
# Order matters: the longer, more specific patterns run first so that a
# shorter one cannot consume part of a match it does not understand.
_PH_REPAIRS: Tuple[Tuple["re.Pattern[str]", str], ...] = (
    # प + matra + ़्ा + फ  ->  फ + matra. The matra does not survive the round
    # trip consistently -- ि and ु come back as themselves, ो comes back where
    # े belongs -- so the three that occur are listed rather than generalised.
    (re.compile(r"प़्ोफ"), "फे"),      # प्रोप़्ोफसर -> प्रोफेसर
    (re.compile(r"पि़्ाफ"), "फि"),     # कार्टोग्रापि़्ाफक -> कार्टोग्राफिक
    (re.compile(r"प़्ाुफ"), "फु"),     # ब्यूटीप़्ाुफल -> ब्यूटीफुल
    (re.compile(r"प़्ाफ"), "फ"),       # काप़्ाफी -> काफी, प्रूप़्ाफ -> प्रूफ
    # व्र [matra] फ -> क्र [matra]. The matra is typed before the फ and stays
    # where it is; only the base letter is wrong.
    (re.compile(r"व्र([ा-ौ]?)फ"), r"क्र\1"),   # व्रिफया -> क्रिया
    # उ + फ -> ऊ at the start of a word, where the pair is really the long
    # vowel; elsewhere the उ is genuine and only the फ is spurious
    # (हाउफस -> हाउस).
    (re.compile(r"(?<![ऀ-ॿ])उफ"), "ऊ"),       # उफर्जा -> ऊर्जा
    (re.compile(r"उफ"), "उ"),                            # हाउफस -> हाउस
    # प्रफी -> फ्री. Restricted to the ी form on purpose: प्रफ is a real
    # sequence (प्रफुल्लित), and only अप्रफीका occurs damaged.
    (re.compile(r"प्रफी"), "फ्री"),                      # अप्रफीका -> अफ्रीका
)

# -- doubled matras --------------------------------------------------------
#
# The same dependent vowel sign twice in a row. No Hindi or Marathi word has
# one -- a matra modifies the consonant before it, and a second identical one
# has nothing to modify -- so collapsing it cannot damage real text.
#
# PyMuPDF produces it on some NCERT fonts, where the matra is drawn as two
# overlapping glyphs and both are mapped. Measured 2026-09-10: ehve102.pdf
# ("न्याय की कुर्सी") at 6.9 per 100 Devanagari characters -- "न्यााय",
# "बााहर", "थाा" -- so the chapter's own title word matched zero chunks and
# questions about the story missed it entirely.
_DOUBLED_MATRA = re.compile(r"([ा-ौॢॣ])\1+")


def repair(text: str) -> str:
    """Apply every known Devanagari extraction repair.

    A no-op on text with no Devanagari in it, and on Devanagari that extracted
    cleanly -- every pattern here is a sequence the script does not otherwise
    produce.
    """
    if not text:
        return text
    text = _DOUBLED_MATRA.sub(r"\1", text)
    for pattern, replacement in _PH_REPAIRS:
        text = pattern.sub(replacement, text)
    return text


def damage_report(text: str) -> List[Tuple[str, str]]:
    """Every repair this text would receive, as (before, after) word pairs.

    For the ingestion report and for checking a new book against the table:
    a font that damages Devanagari some OTHER way will show up as a book with
    no repairs and poor Hindi answers, which is the case worth being able to
    tell apart from this one.
    """
    pairs: List[Tuple[str, str]] = []
    for word in text.split():
        fixed = repair(word)
        if fixed != word:
            pairs.append((word, fixed))
    return pairs
