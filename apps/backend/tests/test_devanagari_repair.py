"""Devanagari the PDF's own font map got wrong.

Every damaged form here was taken from the live Class X Geography library on
2026-09-20 -- 59 distinct forms across 49 occurrences -- and every expected
result is the word the printed page actually shows. Pinned rather than
generated, because the rules are a table derived from one font's behaviour and
the only thing that makes them safe is that each one was checked against a
real word.

The control cases matter as much as the repairs. `साफ`, `क्षेत्रफल` and
`प्रफुल्लित` contain the same letters the table matches on and are correct as
extracted; a rule that touches them is worse than no rule, because it damages
text that arrived intact.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.devanagari import damage_report, repair  # noqa: E402


# (damaged, correct) -- observed in the corpus, in descending frequency.
DAMAGED = [
    ("उफर्जा", "ऊर्जा"),                     # 36x, and in a CHAPTER TITLE
    ("व्रिफयाकलाप", "क्रियाकलाप"),           # 8x, also a heading
    ("प्रव्रिफया", "प्रक्रिया"),
    ("व्रिफयाओं", "क्रियाओं"),
    ("प्रोप़्ोफसर", "प्रोफेसर"),
    ("कार्यव्रफम", "कार्यक्रम"),
    ("उफपरी", "ऊपरी"),
    ("काप़्ाफी", "काफी"),
    ("उफर्ध्वाधर", "ऊर्ध्वाधर"),
    ("अप्रफीका", "अफ्रीका"),
    ("उफष्मा", "ऊष्मा"),
    ("कार्टोग्राप़्ाफी", "कार्टोग्राफी"),
    ("व्रिफया", "क्रिया"),
    ("व्रफांति", "क्रांति"),
    ("पाठ्यव्रफम", "पाठ्यक्रम"),
    ("व्रफमशः", "क्रमशः"),
    ("व्रिफयाएँ", "क्रियाएँ"),
    ("चव्रफ", "चक्र"),
    ("उफँचाई", "ऊँचाई"),
    ("उफपर", "ऊपर"),
    ("व्रफम", "क्रम"),
    ("सूव्रफोस", "सूक्रोस"),
    ("पुनर्चव्रफण", "पुनर्चक्रण"),
    ("उफबड़-खाबड़", "ऊबड़-खाबड़"),
    ("कार्टोग्रापि़्ाफक", "कार्टोग्राफिक"),
    ("ऑप़्ाफ", "ऑफ"),
    ("हाउफस", "हाउस"),
    ("फोटोग्राप़्ाफ", "फोटोग्राफ"),
    ("प्रूप़्ाफ", "प्रूफ"),
    ("व्रिफयात्मक", "क्रियात्मक"),
    ("चव्रफण", "चक्रण"),
    ("ब्यूटीप़्ाुफल", "ब्यूटीफुल"),
    ("जलाव्रफांतता", "जलाक्रांतता"),
]

# Correct as extracted. Each one contains a sequence the table matches near.
UNTOUCHED = [
    "साफ",            # bare ाफ
    "काफी",           # already correct; काप़्ाफी is the damaged form
    "क्षेत्रफल",      # ्रफ, but त्र not व्र
    "प्रफुल्लित",     # प्रफ, which is why the प्रफ rule requires a following ी
    "व्रत",           # व्र with no फ
    "मृदा",
    "महाराष्ट्र",
    "The English text is untouched.",
    "",
]


@pytest.mark.parametrize("damaged,correct", DAMAGED)
def test_damaged_word_is_repaired(damaged, correct):
    assert repair(damaged) == correct


@pytest.mark.parametrize("text", UNTOUCHED)
def test_correct_text_is_left_alone(text):
    assert repair(text) == text


def test_repair_is_idempotent():
    """A second pass must change nothing, or the table has a cycle in it."""
    for damaged, _ in DAMAGED:
        once = repair(damaged)
        assert repair(once) == once


def test_a_chapter_title_becomes_searchable():
    """Why this is worth a table rather than a shrug.

    The heading is also the breadcrumb every chunk beneath it is embedded
    with, so one broken title degrades a whole chapter's retrieval. A student
    asking about ऊर्जा could not match the energy-resources chapter, because
    the chapter's own heading did not contain the word.
    """
    assert repair("खनिज तथा उफर्जा संसाधन") == "खनिज तथा ऊर्जा संसाधन"


def test_doubled_matras_still_collapse():
    """The pre-existing repair, moved here from pdf_text and kept working."""
    assert repair("न्यााय") == "न्याय"
    assert repair("बााहर") == "बाहर"
    assert repair("थाा") == "था"


def test_damage_report_names_what_changed():
    pairs = damage_report("खनिज तथा उफर्जा संसाधन और व्रिफयाकलाप")
    assert ("उफर्जा", "ऊर्जा") in pairs
    assert ("व्रिफयाकलाप", "क्रियाकलाप") in pairs
    assert len(pairs) == 2


def test_both_pipelines_apply_the_same_repair():
    """`pdf_text` and the structural pipeline must not drift apart.

    They ran different repair tables before this module existed: pdf_text had
    the doubled-matra rule and the structural pipeline had none.
    """
    from app.services.rag.ingestion.normalize import clean
    from app.services.rag.pdf_text import _normalise_characters

    damaged = "खनिज तथा उफर्जा संसाधन"
    assert _normalise_characters(damaged) == "खनिज तथा ऊर्जा संसाधन"
    assert clean(damaged) == "खनिज तथा ऊर्जा संसाधन"
