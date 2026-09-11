"""Carrying the previous question into retrieval, and when not to.

Both directions are silent failures, which is why both are pinned here:

  not carrying when we should -- "How can we reduce it?" retrieved soil
  erosion and the balanced-diet pyramid at 0.33-0.36, inside the 0.42 gate,
  and the tutor answered a friction question from them (exp004, 11 Sep).

  carrying when we should not -- "what is photosynthesis?" asked after a
  chemistry question retrieves nothing on its own, which is correct and is what
  lets the tutor say so. Carried, it retrieved ATOMIC NUMBER, cleared the gate,
  and answered botany out of the chemistry chapter (multilingual branch).

Ported from the multilingual branch (a47bee3); the exp004 cases, the setting
and the budget are this branch's own.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.routers import chat  # noqa: E402
from app.services.rag import retrieval  # noqa: E402
from app.services.rag.followup import (  # noqa: E402
    embedding_text,
    is_context_dependent,
)
from app.services.rag.retrieval import (  # noqa: E402
    build_context_block,
    retrieval_query,
    within_budget,
)
from app.services.rag.store import Retrieved  # noqa: E402
from app.services.sessions import Session  # noqa: E402


# -- which questions lean on the previous turn -----------------------------

# The ten follow-ups of the exp004 benchmark. Six of them left their chapter
# on the target; all ten have to be caught.
EXP004_FOLLOWUPS = [
    "Why does it change length during the day?",
    "How can we reduce it?",
    "Which direction does it act in?",
    "Which substances do this?",
    "How do they change from one to another?",
    "Where is its fulcrum?",
    "How does it reach our ears?",
    "What happens when we bring two of them together?",
    "Which of these is in the elbow?",
    "Why do we need it?",
]

# And its ten topic questions, each asked after another topic in a real
# session. None may be carried: that is the photosynthesis failure.
EXP004_TOPICS = [
    "What is a shadow?",
    "What is frictional force?",
    "What is gravitational force?",
    "What is sublimation?",
    "What are the solid, liquid and gaseous states?",
    "What is a lever?",
    "How is sound produced?",
    "What are the poles of a magnet?",
    "What are the types of joints in our body?",
    "What is a balanced diet?",
]


@pytest.mark.parametrize("question", EXP004_FOLLOWUPS + [
    "What are the particles inside it?",
    "Which of them carries a positive charge?",
    "How does that decide the atomic number?",
    "Can you explain this again?",
    "इसमें कौन से कण होते हैं?",
    "उसका आवेश क्या है?",
])
def test_a_question_that_names_no_topic_is_flagged(question):
    assert is_context_dependent(question)


@pytest.mark.parametrize("question", EXP004_TOPICS + [
    "What is an atom?",
    "What is photosynthesis?",
    "Why do we need clean drinking water?",
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
        "How can we reduce it?", "What is frictional force?"
    ) == "What is frictional force? How can we reduce it?"


def test_a_standalone_question_is_embedded_as_asked():
    assert embedding_text(
        "What is a lever?", "How can we reduce it?"
    ) == "What is a lever?"


def test_the_first_question_of_a_session_has_nothing_to_carry():
    for previous in (None, ""):
        assert embedding_text("Why do we need it?", previous) == "Why do we need it?"


def test_only_one_turn_is_carried_not_the_answer():
    """The previous ANSWER is the model's own prose and several times longer;
    averaging it into the vector drowns the thing being asked about."""
    carried = embedding_text("What is inside it?", "What is an atom?")
    assert carried.count("?") == 2, "exactly one previous question, and no answer"


def test_the_setting_turns_carrying_off(monkeypatch):
    """RAG_CARRY_FOLLOWUPS=0 is the A/B switch for the benchmark: off must
    mean the question is searched exactly as typed."""
    monkeypatch.setattr(settings, "rag_carry_followups", False)
    assert retrieval_query(
        "How can we reduce it?", "What is frictional force?"
    ) == "How can we reduce it?"
    monkeypatch.setattr(settings, "rag_carry_followups", True)
    assert retrieval_query(
        "How can we reduce it?", "What is frictional force?"
    ) == "What is frictional force? How can we reduce it?"


# -- the search itself embeds the carried text -------------------------------

class _FakeStore:
    is_open = True

    def search(self, *args, **kwargs):
        return []


def _embedded_text(monkeypatch, question, previous):
    seen = []

    async def fake_embed(text):
        seen.append(text)
        return [0.0]

    monkeypatch.setattr(retrieval, "embed_query", fake_embed)
    asyncio.run(retrieval.retrieve(
        _FakeStore(), question, grade=6, subject=None, previous_question=previous
    ))
    return seen


def test_retrieve_embeds_the_carried_question(monkeypatch):
    assert _embedded_text(monkeypatch, "Why do we need it?", "What is a balanced diet?") == [
        "What is a balanced diet? Why do we need it?"
    ]


def test_retrieve_embeds_a_new_topic_as_typed(monkeypatch):
    assert _embedded_text(monkeypatch, "What is a lever?", "Why do we need it?") == [
        "What is a lever?"
    ]


def test_the_chat_turn_hands_its_previous_question_to_retrieval(monkeypatch):
    captured = {}

    async def fake_retrieve(store, question, **kwargs):
        captured.update(kwargs, question=question)
        return []

    monkeypatch.setattr(chat, "retrieve", fake_retrieve)
    asyncio.run(chat._retrieve_context(
        "How can we reduce it?", None, "What is frictional force?"
    ))
    assert captured["question"] == "How can we reduce it?"
    assert captured["previous_question"] == "What is frictional force?"


# -- where the previous question comes from --------------------------------

def test_the_session_looks_past_the_question_being_answered():
    """The current turn is already on the session by the time retrieval runs,
    so the search has to start one behind it."""
    session = Session("s1")
    session.add("user", "What is frictional force?")
    session.add("assistant", "Friction acts against the direction of motion.")
    session.add("user", "How can we reduce it?")
    assert session.previous_question() == "What is frictional force?"


def test_the_first_turn_of_a_session_has_no_previous_question():
    session = Session("s1")
    session.add("user", "What is frictional force?")
    assert session.previous_question() is None


def test_assistant_turns_are_not_mistaken_for_questions():
    session = Session("s1")
    session.add("user", "What is an atom?")
    session.add("assistant", "It is the smallest particle.")
    session.add("user", "And what is inside it?")
    assert session.previous_question() == "What is an atom?"


# -- what the model actually reads -----------------------------------------

def _hit(chars, page=1):
    return Retrieved(
        chunk_id=page, text="x" * chars, heading="", page_start=page,
        page_end=page, distance=0.2, document_title="Book", grade=6,
        subject="Science",
    )


def test_the_budget_cuts_the_second_passage_behind_a_long_first(monkeypatch):
    """exp004, magnet poles: a 1,193-character exercise page at #1 left no room
    for the 233-character definition at #2, which was cited but never read."""
    monkeypatch.setattr(settings, "rag_context_max_chars", 1200)
    assert [h.page_start for h in within_budget([_hit(1193, 121), _hit(233, 117)])] == [121]
    assert "[2]" not in build_context_block([_hit(1193, 121), _hit(233, 117)])


def test_the_budget_keeps_an_oversized_first_passage(monkeypatch):
    monkeypatch.setattr(settings, "rag_context_max_chars", 1200)
    assert len(within_budget([_hit(1500)])) == 1


def test_passages_that_fit_are_all_kept(monkeypatch):
    monkeypatch.setattr(settings, "rag_context_max_chars", 1200)
    assert len(within_budget([_hit(600, 1), _hit(500, 2)])) == 2
