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
