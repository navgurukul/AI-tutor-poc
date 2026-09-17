"""Turning a PDF's visual lines back into the book's sentences and sections.

Every line in here is the Class 6 book's own text, as pypdf extracts it --
including the double spaces, the spaced question marks and the "l" that the
round bullet comes out as -- because the failures below happened on those pages.

What went wrong before this, measured over the whole book:

    a paragraph break mid-sentence    2,365 places
    definitions split in two          65 of 103
    heading labels on chunks          251, most of them fragments or captions

The cause was a single rule: a line shorter than 78% of the page's longest line
ended its paragraph. On a two-column page one full-width line sets a bar the
body text never reaches, so p.81 stored "The force applied by means of a
machine" and "is called mechanical force." as two separate paragraphs -- and the
tutor, handed two fragments that each define nothing, answered from memory.

The shape of the fix is to read each line against the next: a lowercase
continuation joins whatever its length, a heading has to be followed by body
text, and length is only asked about once a sentence has ended.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.pdf_text import (  # noqa: E402
    _measure,
    _reflow,
    is_section_heading,
    looks_like_heading,
)


def paragraphs(*lines):
    return _reflow("\n".join(lines)).split("\n\n")


# p.81, column lines as extracted. The widest line on the page is 69 characters,
# the body 45-52: the old threshold of 54 split all of these.
P81 = (
    "We use different machines for doing many tasks.",
    "Muscular force is used for running some machines.",
    "Some machines are run by using electricity or",
    "fuel. Machines like the latter are called 'automatic",
    "machines', because a mechanical force is used",
    "here. For example, sewing machine, electric pump,",
    "washing machine, mixer, etc. Make a list of other",
    "such machines.",
    "The force applied by means of a machine",
    "is called mechanical force.",
    " The force applied with the help of muscles is called muscular force.",
)


# --------------------------------------------------------------------------
# sentences stay whole
# --------------------------------------------------------------------------
def test_the_mechanical_force_definition_is_one_sentence():
    assert "The force applied by means of a machine is called mechanical force." in paragraphs(*P81)


def test_one_full_width_line_does_not_shred_the_column():
    """The failure itself: 11 lines used to come back as 11 paragraphs."""
    assert len(paragraphs(*P81)) <= 3


def test_a_lowercase_line_continues_whatever_its_length():
    """p.26, beside a full-width line that set the old bar at 54 characters."""
    got = paragraphs("Wild animals that hunt other animals for food",
                     "are called predators, for example, tigers, lions,",
                     "wolves, leopards.",
                     "l The smallest unit of a living thing is the cell and all things are made of it.")
    assert ("Wild animals that hunt other animals for food are called predators, "
            "for example, tigers, lions, wolves, leopards.") in got


def test_a_line_trailing_off_continues_into_a_capitalised_word():
    """p.103: the line ends on "of"; nothing that ends on "of" is finished."""
    assert len(paragraphs("The substance around a source of",
                          "Sound travels through it.")) == 1


def test_hyphenated_words_are_still_rejoined():
    assert "tissues" in _reflow("plant tis-\nsues are of two types.")


def test_empty_page_is_survivable():
    assert _reflow("") == ""
    assert _reflow("\n\n  \n") == ""
    assert _measure(["", "", ""]) == 0.0           # an image-only page, lines stripped as _reflow does


# --------------------------------------------------------------------------
# what is and is not a heading
# --------------------------------------------------------------------------
def test_a_numbered_section_heading_opens_its_own_block():
    got = paragraphs("2. Mechanical force", "We use different machines for doing many tasks.")
    assert got[0] == "2. Mechanical force"


def test_an_activity_step_is_not_a_heading():
    """p.111: the step matched the numbered-heading rule, and "Next, you move
    further away from him" became the label of the shadow chapter's chunks."""
    got = paragraphs("3.  Next, you move further away from him", "and towards him again.")
    assert got == ["3. Next, you move further away from him and towards him again."]


def test_a_heading_is_never_continued_by_a_lowercase_line():
    got = paragraphs("1. Determine the directions in the class or",
                     "laboratory. Tie a thread to the centre of a bar magnet")
    assert len(got) == 1


def test_headings_do_not_end_on_a_function_word():
    for fragment in ("Characteristics of", "Determine the directions in the class or",
                     "Textbook Production and", "Jupiter, Saturn, Uranus and"):
        assert not looks_like_heading(fragment), fragment


def test_headings_do_not_start_lowercase():
    assert not looks_like_heading("the Indian scientist Sir C. V. Raman")


def test_a_figure_caption_is_not_a_heading():
    """"10.8 : Frictional force" is Figure 10.8. As a heading it opened a section
    wherever the figure sat."""
    assert not looks_like_heading("10.8 : Frictional force")


def test_a_caption_goes_with_its_tail_and_takes_nothing_else():
    """Out of reading order, a caption lands mid-definition; it is furniture."""
    got = paragraphs("1.3 : Proportions of the various", "gases in the air",
                     "All the above pictures show large scale emission of smoke.")
    assert got == ["All the above pictures show large scale emission of smoke."]


def test_a_caption_does_not_take_the_body_text_after_it():
    """p.97: extraction put the caption mid-paragraph, so the body resumes in
    lowercase. Owned by the caption, the lever definition was deleted with it."""
    got = paragraphs("12.8 :  Lifting a paperweight",
                     "less force is required to lift the paperweight. Such a",
                     "lever is called a lever of the first order.",
                     "2. The picture shows how we use an opener to remove")
    assert any("Such a lever is called a lever of the first order." in p for p in got)


def test_captions_do_not_interrupt_a_definition():
    got = paragraphs("While falling, its speed goes on increasing all the",
                     "time due to gravitational force.",
                     "10.5 : Falling down of a ball and a mango",
                     "10.3 : Lifting a weight",
                     "The force applied by the earth to pull objects towards itself",
                     "is called gravitational force.")
    assert not any(p.startswith("10.") for p in got)
    assert "The force applied by the earth to pull objects towards itself is called gravitational force." in got


def test_diagram_labels_do_not_join_into_a_heading():
    """Joined, "Candle", "Plastic", "Iron" read as a Title-case heading."""
    got = paragraphs("Candle", "Plastic", "Iron", "Why does this happen ?")
    assert "Candle Plastic Iron" not in got


# --------------------------------------------------------------------------
# list items and exercise options
# --------------------------------------------------------------------------
def test_list_items_stay_separate():
    """The exercise filter judges one item per paragraph."""
    assert paragraphs("1.  Send the friend closer to the wall.",
                      "2.  Ask the friend to come towards you.") == [
        "1. Send the friend closer to the wall.",
        "2. Ask the friend to come towards you.",
    ]


def test_a_wrapped_item_is_one_paragraph():
    assert paragraphs("1. Spread small pieces of paper on a table. Rub a piece of",
                      "thermocol or an inflated balloon against silk cloth and",
                      "bring it near these pieces.") == [
        "1. Spread small pieces of paper on a table. Rub a piece of thermocol or "
        "an inflated balloon against silk cloth and bring it near these pieces."
    ]


def test_an_item_does_not_swallow_the_lesson_after_it():
    """p.128: joined, the whole paragraph opened on "(c)", and the exercise filter
    condemned "We should study phenomena like meteor falls" along with it."""
    got = paragraphs("(c) Jupiter is the biggest planet.",
                     "Science tries to explain different events occurring in the universe.")
    assert got[-1] == "Science tries to explain different events occurring in the universe."


def test_a_list_of_short_items_is_not_a_heading():
    got = paragraphs("3. Forest fires", "4. Increased risk due to high population density.")
    assert got == ["3. Forest fires", "4. Increased risk due to high population density."]


# --------------------------------------------------------------------------
# the chunker's question: does this paragraph open a section?
# --------------------------------------------------------------------------
def test_a_heading_followed_by_prose_opens_a_section():
    assert is_section_heading(["2. Mechanical force", "We use different machines for doing many tasks."], 0)


def test_a_table_header_does_not_open_a_section():
    """p.45: before this, "Substance Freezing point Boiling point" labelled the
    sublimation section that follows the table."""
    assert not is_section_heading(["Substance Freezing point Boiling point", "Candle", "Plastic"], 0)


def test_a_chapter_title_above_its_first_section_opens_one():
    assert is_section_heading(["Fun with Magnets", "Magnetic Power", "Magnets attract iron objects."], 0)


def test_a_heading_last_on_its_page_is_kept():
    """Its body is on the next page."""
    assert is_section_heading(["Some text that ends here.", "Gravitational Force"], 1)


def test_body_text_does_not_open_a_section():
    assert not is_section_heading(["We use different machines for doing many tasks."], 0)
