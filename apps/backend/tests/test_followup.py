"""Carrying the previous question into retrieval, and when not to.

Both directions are silent failures, which is why both are pinned here:

  not carrying when we should -- "what are the particles inside it?" retrieved
  a page on evaporation at 0.423, inside the English ceiling, and the tutor
  cited it for a question about atomic structure.

  carrying when we should not -- "what is photosynthesis?" asked after a
  chemistry question retrieves nothing on its own, which is correct and is what
  lets the tutor say so. Carried, it retrieves ATOMIC NUMBER at 0.421, clears
  the ceiling, and answers botany out of the chemistry chapter.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import Message  # noqa: E402
from app.services.rag.followup import (  # noqa: E402
    embedding_text,
    is_context_dependent,
)
from app.services.sessions import Session  # noqa: E402


# -- which questions lean on the previous turn -----------------------------

@pytest.mark.parametrize("question", [
    "What are the particles inside it?",
    "Which of them carries a positive charge?",
    "How does that decide the atomic number?",
    "Can you explain this again?",
    "Why is it important?",
    "इसमें कौन से कण होते हैं?",
    "उसका आवेश क्या है?",
])
def test_a_question_that_names_no_topic_is_flagged(question):
    assert is_context_dependent(question)


@pytest.mark.parametrize("question", [
    "What is an atom?",
    "What is photosynthesis?",
    "Why do we need clean drinking water?",
    "What is the atomic number of carbon?",
    "Where are the electrons found?",
    "परमाणु क्या है?",
])
def test_a_question_that_stands_on_its_own_is_left_alone(question):
    """The topic-change case in particular. Nobody writes "what is
    photosynthesis?" with a dangling "it", which is exactly why this test
    separates a new topic from a follow-up where a distance threshold cannot --
    the contentless question's distances look perfectly healthy."""
    assert not is_context_dependent(question)


# -- what actually gets embedded -------------------------------------------

def test_the_previous_question_is_prepended_for_a_follow_up():
    assert embedding_text(
        "What are the particles inside it?", "What is an atom?"
    ) == "What is an atom? What are the particles inside it?"


def test_a_standalone_question_is_embedded_as_asked():
    assert embedding_text(
        "What is photosynthesis?", "What is an atom?"
    ) == "What is photosynthesis?"


def test_the_first_question_of_a_session_has_nothing_to_carry():
    for previous in (None, ""):
        assert embedding_text("Why is it important?", previous) == "Why is it important?"


def test_only_one_turn_is_carried_not_the_answer():
    """The previous ANSWER is the model's own prose and several times longer;
    averaging it into the vector drowns the thing being asked about."""
    carried = embedding_text("What is inside it?", "What is an atom?")
    assert carried.count("?") == 2, "exactly one previous question, and no answer"


# -- where the previous question comes from --------------------------------

def test_the_session_looks_past_the_question_being_answered():
    """The current turn is already on the session by the time retrieval runs,
    so the search has to start one behind it."""
    session = Session("s1")
    session.add("user", "What is an atom?")
    session.add("assistant", "An atom is the smallest particle of an element.")
    session.add("user", "What is inside it?")
    assert session.previous_question() == "What is an atom?"


def test_the_first_turn_of_a_session_has_no_previous_question():
    session = Session("s1")
    session.add("user", "What is an atom?")
    assert session.previous_question() is None


def test_assistant_turns_are_not_mistaken_for_questions():
    session = Session("s1")
    session.add("user", "What is an atom?")
    session.add("assistant", "It is the smallest particle.")
    session.add("user", "And what is inside it?")
    assert session.previous_question() == "What is an atom?"
