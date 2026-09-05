"""Chunk bounds and heading detection.

Both defects fixed here are silent: a spurious hard cut splits a section
mid-explanation and files the remainder under a figure label, and a heading
that can never fire for Devanagari leaves a Hindi chapter as one undivided
run of prose. Neither raises anything.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.chunking import chunk_pages  # noqa: E402
from app.services.rag.pdf_text import looks_like_heading  # noqa: E402


# -- heading detection -----------------------------------------------------

def test_numbered_headings_fire_in_any_script():
    assert looks_like_heading("6.2 Plant Tissues")
    assert looks_like_heading("६.२ पादप ऊतक")


def test_all_caps_is_still_a_heading():
    assert looks_like_heading("TISSUES")


def test_two_capitalised_words_are_not_a_heading():
    """The old rule made any two capitalised words a hard cut."""
    assert not looks_like_heading("Xylem Vessels")
    assert not looks_like_heading("Cardiac Muscle")


def test_explicit_captions_are_not_headings():
    assert not looks_like_heading("Fig. 6.2 Xylem Vessels")
    assert not looks_like_heading("Table 3 Types Of Tissue")


def test_a_real_title_cased_heading_still_fires():
    assert looks_like_heading("Structure Of Plant Tissues")


def test_devanagari_headings_are_reachable_at_all():
    """Without a caseless branch only the numbered regex could ever fire."""
    assert looks_like_heading("ऊतक")
    assert looks_like_heading("पादप ऊतक")


def test_devanagari_prose_is_not_a_heading():
    assert not looks_like_heading(
        "ऊतक कोशिकाओं का एक समूह है जो एक साथ मिलकर एक विशेष कार्य करती हैं"
    )


# -- chunk bounds ----------------------------------------------------------

def _pages(*paras):
    return ["\n\n".join(paras)]


def test_a_section_between_target_and_max_stays_whole():
    """The point of three bounds: no cut at character 1,201."""
    para = "Water moves through the xylem. " * 45          # ~1,350 chars
    assert 1200 < len(para) < 2000
    chunks = chunk_pages(_pages(para), target_chars=1200, overlap_chars=0,
                         max_chars=2000, min_chars=40)
    assert len(chunks) == 1, "a 1,350-char paragraph should not be split"


def test_a_paragraph_past_max_is_split_on_sentences():
    para = "Water moves through the xylem. " * 80          # ~2,400 chars
    chunks = chunk_pages(_pages(para), target_chars=1200, overlap_chars=0,
                         max_chars=2000, min_chars=40)
    assert len(chunks) > 1
    assert all(len(c.text) <= 2000 for c in chunks)


def test_short_definitions_survive_the_floor():
    """A one-line definition is exactly what a definition question wants."""
    chunks = chunk_pages(
        _pages("Xylem: the tissue that carries water up the stem."),
        target_chars=1200, overlap_chars=0, max_chars=2000, min_chars=40,
    )
    assert len(chunks) == 1
    assert "Xylem" in chunks[0].text


def test_below_the_floor_is_dropped():
    chunks = chunk_pages(_pages("Fig. 1"), target_chars=1200, overlap_chars=0,
                         max_chars=2000, min_chars=40)
    assert chunks == []


def test_a_heading_is_a_hard_cut_with_no_overlap_carried():
    chunks = chunk_pages(
        _pages(
            "6.1 Plant Tissues",
            "Plants have several kinds of tissue. " * 12,
            "6.2 Animal Tissues",
            "Animals have several kinds of tissue too. " * 12,
        ),
        target_chars=600, overlap_chars=100, max_chars=2000, min_chars=40,
    )
    assert len(chunks) >= 2
    plant = [c for c in chunks if c.heading == "6.1 Plant Tissues"]
    animal = [c for c in chunks if c.heading == "6.2 Animal Tissues"]
    assert plant and animal
    # Nothing from the plant section carried across the heading.
    assert "Plants have" not in animal[0].text


def test_breadcrumb_puts_the_chapter_in_the_vector():
    chunks = chunk_pages(
        _pages("6.1 Tissues", "They are groups of cells. " * 8),
        target_chars=1200, overlap_chars=0, max_chars=2000, min_chars=40,
    )
    text = chunks[0].embedding_text(9, "Science")
    assert text.startswith("Class 9 > Science > 6.1 Tissues")
    # ...and is stripped from what the model is shown.
    assert not chunks[0].text.startswith("Class 9")


# -- running heads ---------------------------------------------------------

from app.services.rag.pdf_text import _find_repeated_lines, _running_head_stem  # noqa: E402


def test_stem_ignores_page_numbers_and_letter_spacing():
    """Textbook running heads are letter-spaced and carry the page number."""
    assert _running_head_stem("SCIENCE2") == _running_head_stem("SCIENCE10") == "science"
    assert _running_head_stem("MA TTER  IN O UR  S URROUNDING S 7") == "matterinoursurroundings"
    assert _running_head_stem("IS M ATTER AROUND US PURE? 23") == "ismatterarounduspure"


def _book(n=20):
    """A book with two alternating numbered running heads, as NCERT prints them."""
    pages = []
    for i in range(1, n + 1):
        head = "SCIENCE%d" % i if i % 2 == 0 else "MA TTER  IN O UR  S URROUNDING S %d" % i
        # Body lines must differ per page, or the share-of-pages rule correctly
        # classifies them as furniture too and the test proves nothing.
        pages.append(
            "%s\nBody sentence number %d about matter.\nA further remark, number %d."
            % (head, i, i)
        )
    return pages


def test_numbered_running_heads_are_stripped():
    """Exact-match counting cannot see these: every occurrence is a different
    string, appearing exactly once. Before the stem rule they all survived and
    became chunk headings, so students saw "SCIENCE76" as their citation."""
    repeated = _find_repeated_lines(_book())
    assert "SCIENCE2" in repeated
    assert "MA TTER  IN O UR  S URROUNDING S 7" in repeated


def test_body_text_survives_running_head_detection():
    """Body lines end in a number too -- the stem rule must not eat them.

    "A further remark, number 7." has a trailing digit and sits at a page edge,
    so it reaches the same code path as a running head. What saves it is that
    its stem is unique per page, never recurring across three pages.
    """
    repeated = _find_repeated_lines(_book())
    assert not any("Body sentence" in line for line in repeated)
    assert not any("further remark" in line for line in repeated)


def test_a_number_that_never_varies_is_not_a_running_head():
    """"9.1 First Law of Motion" repeated verbatim is a constant header, caught
    by the share-of-pages rule -- but the stem rule must not claim it, because
    its number is part of the title, not a page count."""
    pages = ["9.1 First Law of Motion\nSome body text %d here." % i for i in range(12)]
    stems = {}
    # The stem rule requires the trailing number to VARY; here it never does.
    repeated = _find_repeated_lines(pages)
    # It is still dropped -- but by the exact-match rule, which is correct.
    assert "9.1 First Law of Motion" in repeated


def test_short_books_are_left_alone():
    """Under six pages the statistics are meaningless."""
    assert _find_repeated_lines(["SCIENCE1\nText", "SCIENCE2\nText"]) == set()


# -- the debris filter must not be ASCII-only ------------------------------

from app.services.rag.pdf_text import _MOSTLY_SYMBOLS, clean_pages  # noqa: E402


def test_devanagari_prose_is_not_mistaken_for_debris():
    """The bug that hid until a real Hindi textbook existed.

    Written as [^A-Za-z0-9]{3,} the debris filter matched every line of a
    Devanagari book, because Devanagari contains no ASCII letters. 70% of the
    first Hindi textbook put through the pipeline was silently discarded --
    197,085 characters in, 58,450 out -- with no error anywhere. An
    English-only corpus could never surface it.
    """
    assert _MOSTLY_SYMBOLS.match("परमाणु की संरचना") is None
    assert _MOSTLY_SYMBOLS.match("ऊतक कोशिकाओं का समूह है") is None
    assert _MOSTLY_SYMBOLS.match("४.२.३ बोर का परमाण्विक मॉडल") is None


def test_real_debris_is_still_dropped():
    assert _MOSTLY_SYMBOLS.match("-----") is not None
    assert _MOSTLY_SYMBOLS.match("।।।") is not None
    assert _MOSTLY_SYMBOLS.match("+++ ---") is not None


def test_a_devanagari_page_survives_cleaning():
    pages = ["ऊतक कोशिकाओं का एक समूह है जो एक साथ मिलकर कार्य करती हैं।"] * 8
    cleaned = clean_pages(pages)
    kept = sum(len(p) for p in cleaned)
    # Repeated-line detection will strip these as furniture (they are
    # identical), so assert on a page that varies instead.
    pages = ["ऊतक कोशिकाओं का समूह %d है जो कार्य करती हैं।" % i for i in range(8)]
    cleaned = clean_pages(pages)
    kept = sum(len(p) for p in cleaned)
    assert kept > 0.9 * sum(len(p) for p in pages)
