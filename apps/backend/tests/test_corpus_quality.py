"""Ingest-time corpus filtering: what must go, and what must never go with it.

Every string in here is the Class 6 book's own text, PDF line breaks and typos
included, because the failures this guards against are failures on real pages
and not on invented ones.

The asymmetry that shapes these tests: a false positive deletes a fact from the
corpus and no later stage can put it back -- the tutor then answers from the
model alone and sounds perfectly fine doing it -- while a false negative leaves
one noisy line in a chunk. So there are more tests below for what survives than
for what goes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.chunking import chunk_pages  # noqa: E402
from app.services.rag.quality import (  # noqa: E402
    clean_heading,
    is_apparatus,
    is_question_only,
    keep_on_exercise_page,
    page_is_exercise,
    strip_apparatus,
)


# --------------------------------------------------------------------------
# the fill-in-the-blank that taught a student magnets backwards
# --------------------------------------------------------------------------
def test_blank_run_is_apparatus():
    """p.121, retrieved FIRST for "What are the poles of a magnet?" in the
    groundedness run of 2026-09-16. The tutor read it and told the student that
    opposite poles repel."""
    assert is_apparatus(
        "(c) There is repulsion between the .......... poles of a magnet, "
        "and attraction between its ............ poles."
    )


def test_the_real_definition_is_not_apparatus():
    """p.117, the sentence that should have been retrieved instead. Identical
    vocabulary, no blanks."""
    assert not is_apparatus(
        "There is repulsion between like poles of a magnet, while there is "
        "attraction between the opposite poles."
    )


def test_three_dots_are_an_ellipsis_not_a_blank():
    """shorten_passage marks a cut with a single ellipsis; only four or more
    dots in a row is a blank the publisher left."""
    assert not is_apparatus("... and the sound also stops.")


# --------------------------------------------------------------------------
# true/false lists, which assert the opposite of the chapter
# --------------------------------------------------------------------------
def test_true_false_items_go_with_their_stem():
    """p.74. Reflow splits the instruction mid-sentence, so "Bones are soft."
    arrives two paragraphs after the words that make it a question. Left in, it
    is a flat assertion that the chapter contradicts."""
    kept = strip_apparatus([
        "3. Right or wrong ? If wrong, write the",
        "correct sentence.",
        "(a) Bones are soft.",
        "(b) The human skeleton protects the",
        "internal organs.",
    ])
    assert not any("Bones are soft" in k for k in kept)


def test_prose_after_an_exercise_run_is_not_swallowed():
    """The suppression must stop at the first real paragraph, or it eats the
    next section."""
    kept = strip_apparatus([
        "1. Fill in the blanks with the proper word.",
        "(a) The place where two or more bones",
        "Joints are the places where two or more than two bones are connected "
        "to each other. Joints are of two types.",
    ])
    assert any("Joints are of two types" in k for k in kept)


# --------------------------------------------------------------------------
# box labels
# --------------------------------------------------------------------------
def test_box_labels_are_apparatus():
    for label in ["Try this.", "Let's try this.", "Do you know ?", "Can you tell ?",
                  "Use your brain power !", "Observe and discuss.", "Activity :",
                  "Always remember...", "Exercise", "What we have learnt-"]:
        assert is_apparatus(label), label


def test_a_label_that_goes_on_to_say_something_is_kept():
    """Anchored at both ends on purpose: only a paragraph that is *only* a label
    is furniture."""
    assert not is_apparatus(
        "Find out how much water your family uses in a day and write it down "
        "in a table, then compare it with the figures given above."
    )


# --------------------------------------------------------------------------
# exercise pages keep their summary
# --------------------------------------------------------------------------
_EXERCISE_PAGE = [
    "1. Fill in the blanks with the proper",
    "word.",
    "(a) The place where two or more bones",
    "are connected is called a .............. .",
    "2. Match the pairs.",
    "(1) Ball and socket joint (a) Knee",
    "(2) Hinge joint (b) Wrist",
    "3. Right or wrong ? If wrong, write the",
    "correct sentence.",
    "(a) Bones are soft.",
    "What we have learnt-",
    "l A diet containing all nutrients in the right quantity is called a "
    "balanced diet.",
    "l Junk food gives us energy but not other nutrients.",
    "Activity :",
    "l Collect pictures of the different",
]


def test_an_exercise_page_is_recognised():
    assert page_is_exercise(_EXERCISE_PAGE)


def test_a_lesson_page_is_not_an_exercise_page():
    """p.83. It ends with two box labels and still is not an exercise."""
    assert not page_is_exercise([
        "When two surfaces rub against each",
        "other, the force of friction comes into play.",
        "It always acts against the direction of",
        "motion.",
        "The smooth surfaces can be easily rubbed against each",
        "other because the force of friction between them is less,",
        "It is possible for us to walk on the ground only because",
        "of the force of friction. If there is no friction, we would",
        "slip and fall.",
        "Try this.",
        "Use your brain power !",
    ])


def test_the_summary_survives_an_exercise_page():
    """Dropping these pages whole was the first version and it removed 20
    declarative summary lines that appear nowhere else in the book -- this one
    among them."""
    kept = " ".join(keep_on_exercise_page(_EXERCISE_PAGE))
    assert "A diet containing all nutrients in the right quantity" in kept
    assert "Junk food gives us energy" in kept


def test_the_exercise_does_not_survive_an_exercise_page():
    kept = " ".join(keep_on_exercise_page(_EXERCISE_PAGE))
    for gone in ["Bones are soft", "Match the pairs", "Ball and socket joint",
                 "Fill in the blanks", "Collect pictures"]:
        assert gone not in kept, gone


# --------------------------------------------------------------------------
# chunks that only ask
# --------------------------------------------------------------------------
def test_a_bare_activity_prompt_is_question_only():
    assert is_question_only(
        "To which part of plants are butterflies and insects attracted ?"
    )


def test_prose_with_a_rhetorical_question_is_not():
    """p.83 asks and then answers. Cutting the question would strand the
    answer, so this is tested at chunk level where the statements are present."""
    assert not is_question_only(
        "A ball rolling over a flat ground stops at a certain distance. Why "
        "does this happen ? When two surfaces rub against each other, the "
        "force of friction comes into play."
    )


# --------------------------------------------------------------------------
# the breadcrumb heading
# --------------------------------------------------------------------------
def test_junk_headings_are_rejected():
    """Every one of these labelled real prose in the shipped index, and went
    into the vector in front of it."""
    for junk in ["28620C", "B", "E", "1000C", "lll",
                 "3. Fill in the blanks with the appropriate",
                 "5. Go toward the left and then to the right",
                 "3. Rub a peacock feather between two pages of a notebook",
                 "7. On what is the sailboat floating ?",
                 "Try this."]:
        assert clean_heading(junk) == "", junk


def test_real_headings_survive_with_their_numbering_stripped():
    assert clean_heading("5. Frictional force") == "Frictional force"
    assert clean_heading("10.8 : Frictional force") == "Frictional force"
    assert clean_heading("3. Gravitational force") == "Gravitational force"
    assert clean_heading("Immovable Joint") == "Immovable Joint"
    assert clean_heading("06.72.01 Identifies materials") == "Identifies materials"


# --------------------------------------------------------------------------
# end to end, and the switch that turns it all off
# --------------------------------------------------------------------------
_PAGES = [
    "\n\n".join([
        "5. Frictional force",
        "When two surfaces rub against each other, the force of friction comes "
        "into play. It always acts against the direction of motion.",
        "Try this.",
        "1. Fill in the blanks.",
        "(a) The force of ....... always acts against motion.",
    ]),
]


def test_chunking_keeps_the_definition_and_drops_the_exercise():
    chunks = chunk_pages(_PAGES, chunk_chars=1200, overlap_chars=180)
    text = " ".join(c.text for c in chunks)
    assert "the force of friction comes into play" in text
    assert "Fill in the blanks" not in text
    assert "always acts against motion" not in text
    assert chunks[0].heading == "Frictional force"


def test_filtering_off_reproduces_the_old_index():
    """RAG_FILTER_CORPUS=0 has to be a real escape hatch: same text, same
    unvalidated heading."""
    chunks = chunk_pages(_PAGES, chunk_chars=1200, overlap_chars=180,
                         drop_exercises=False)
    text = " ".join(c.text for c in chunks)
    assert "Fill in the blanks" in text
    assert chunks[0].heading == "5. Frictional force"


def test_the_breadcrumb_falls_back_when_a_heading_is_junk():
    from app.services.rag.chunking import Chunk

    chunk = Chunk(0, "Some prose about magnets.", "", 1, 1)
    assert chunk.embedding_text(6, "Science").startswith("Class 6 > Science\n\n")
    labelled = Chunk(0, "Some prose.", "Frictional force", 1, 1)
    assert labelled.embedding_text(6, "Science").startswith(
        "Class 6 > Science > Frictional force"
    )
    assert labelled.embedding_text(6, "Science", breadcrumb=False) == "Some prose."


# --------------------------------------------------------------------------
# numbered exercise questions, split before their own question mark
# --------------------------------------------------------------------------
def test_a_numbered_exercise_question_is_apparatus():
    """p.51. This fragment was the TOP hit for "What is sublimation?" after the
    first pass of filtering -- a near-perfect embedding match for the student's
    question that answers none of it, ranked above the definition on p.46."""
    assert is_apparatus("4. What is sublimation ? Write the")
    assert is_apparatus("2. Why is it said that - ?")


def test_a_numbered_heading_without_a_question_is_kept():
    """The rule must not reach section headings, which are also numbered."""
    assert not is_apparatus("1. Linear motion")
    assert not is_apparatus("5. Frictional force")


def test_prose_that_asks_and_answers_is_kept():
    """Long, unnumbered, and the answer follows -- the case the numbering test
    exists to stay away from."""
    assert not is_apparatus(
        "A ball rolling over a flat ground stops at a certain distance. Why "
        "does this happen ? When two surfaces rub against each other, the "
        "force of friction comes into play."
    )


def test_a_rejected_heading_survives_as_body_text():
    """Reflow calls a lot of ordinary prose a heading on a narrow column, and a
    rejected heading used to be consumed and thrown away -- which deleted the
    p.96 definition of the fulcrum from the corpus outright. Caught by
    groundedness_eval.py --check-evalset, which is what that check is for."""
    pages = ["\n\n".join([
        "1. The support at which the rod of a lever is",
        "rested is called the 'fulcrum of a lever'. The lever rotates about "
        "the fulcrum.",
    ])]
    text = " ".join(c.text for c in chunk_pages(pages, 1200, 180))
    assert "The support at which the rod of a lever is" in text
    assert "rested is called the 'fulcrum of a lever'" in text
