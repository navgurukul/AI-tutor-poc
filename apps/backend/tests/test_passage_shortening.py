"""Shortening a passage to the question, and keeping it stable across turns.

The budget always keeps the top passage whole, so before this a single long
passage set the wait: every turn still over 6s at 800 characters in exp006
was one passage of 950-1,200 characters. rag_passage_max_chars bounds it.

Two ways this goes wrong silently, both pinned here:

  cutting out the answer -- the passage still reaches the prompt and is
  still cited, so nothing looks missing. The sweat passage opens with seven
  sentences about skin; a picker that counts plain matches keeps those and
  drops "It helps to reduce the temperature of the body", the actual "why".

  re-cutting a passage the last turn already sent -- a follow-up that
  retrieves its topic question's passage only reuses Ollama's cache if the
  excerpt is the same string. Cut around the follow-up's own words, it is
  not, and a 1.5s follow-up goes back to full prefill.

The two passages are the Class 6 book's own text, PDF line wraps included.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.routers import chat  # noqa: E402
from app.services.rag.retrieval import (  # noqa: E402
    build_context_block,
    prompt_hits,
    shorten_passage,
)
from app.services.rag.store import Retrieved  # noqa: E402
from app.services.sessions import Session  # noqa: E402

# p. 111, retrieved first for "What is a shadow?" in exp006. The definition is
# its last sentence.
SHADOW = (
    "of the friend.\n\nAsk your friend to stand at a certain distance from you in a\n\n"
    "big room and obtain the shadow of your friend on the wall with the\n\n"
    "help of a torch. Now carry out the following actions. Observe and\n\n"
    "make a note of the changes taking place in the shadow.\n\n"
    "The shadow of an object is formed only when light does not pass through the "
    "object. The kind of shadow it forms depends upon the relative distances between "
    "the source of light, the object and the surface or the screen on which the "
    "shadow is formed. The shadow of an object formed due to sunlight is long in the "
    "mornings and evenings and short in the afternoon. We can easily note these "
    "changes if we observe the trees along the roadside. This change in the shadow "
    "depends on the source of light, the object and also on the surface on which the "
    "shadow is formed.\n\nIf an opaque object comes in the way of a light source, "
    "light does not pass through it. As a result, the light does not reach a wall or "
    "any other surface on the other side of the object. That part remains dark. This "
    "dark part is called the 'shadow of the object'. Try this."
)

# pp. 71-72, retrieved first for "Why does our skin sweat?". Opens on joints,
# then seven sentences of skin before it reaches sweat.
SWEAT = (
    "Bones cannot move.\n\nExample : bones of\n\nthe skull.\n\n(Other than the lower\n\n"
    "jaw)\n\nJoints\n\nTry this.\n\nWhich organ helps us to sense whether something "
    "is hot or cold, rough or smooth, etc. ?\n\nThe skin\n\nThe skin is an important "
    "and large organ of all living things. The skin has hair. There are nails on the "
    "skin at the tips of the fingers and toes. The skin gives us the sense of touch. "
    "The skin is an important sensory organ of the body. What happens when we walk or "
    "play in the hot sun ?\n\nWhen we walk or play in the sun, we get tired, but at "
    "the same time our skin becomes wet. This is because of sweat. In the skin, there "
    "are glands which secrete sweat. They are called sweat glands. After playing in "
    "the hot sun or after hard physical labour, the temperature of the body rises. "
    "Then sweat is released. It helps to reduce the temperature of the body. Our body "
    "temperature usually remains constant at approximately 37 0C."
)


def _hit(text, chunk_id=1):
    return Retrieved(
        chunk_id=chunk_id, text=text, heading="", page_start=chunk_id,
        page_end=chunk_id, distance=0.2, document_title="Book", grade=6,
        subject="Science",
    )


def _flat(text):
    return " ".join(text.split())


# -- what is kept -----------------------------------------------------------

def test_a_passage_that_fits_is_left_exactly_as_it_was():
    text = "Joints are the places\n\nwhere two bones meet."
    assert shorten_passage(text, "What is a joint?", 600) is text


def test_a_long_passage_is_cut_to_the_limit_and_says_so():
    out = shorten_passage(SHADOW, "What is a shadow?", 600)
    assert len(SHADOW) > 1000
    assert len(out) <= 600
    assert out.startswith("… ")


def test_a_what_is_question_keeps_the_definition_and_what_it_leans_on():
    out = _flat(shorten_passage(SHADOW, "What is a shadow?", 600))
    assert "This dark part is called the 'shadow of the object'." in out
    assert "That part remains dark." in out


def test_a_why_question_keeps_the_explanation_not_the_most_repeated_word():
    out = _flat(shorten_passage(SWEAT, "Why does our skin sweat?", 600))
    assert "It helps to reduce the temperature of the body." in out
    assert "Bones cannot move." not in out


def test_a_passage_that_matches_nothing_keeps_its_opening():
    out = shorten_passage(SHADOW, "Who won the football world cup?", 600)
    assert out.startswith("of the friend. Ask your friend")
    assert out.endswith(" …")


def test_text_with_no_full_stop_still_fits():
    """Tables and exercise pages extract as one endless 'sentence'."""
    assert len(shorten_passage("x" * 1193, "anything", 600)) <= 600
    assert len(shorten_passage("word " * 300, "word", 600)) <= 600


def test_zero_turns_shortening_off(monkeypatch):
    monkeypatch.setattr(settings, "rag_passage_max_chars", 0)
    assert shorten_passage(SHADOW, "What is a shadow?") == SHADOW


# -- how it meets the budget ------------------------------------------------

def test_a_long_top_passage_no_longer_sets_the_wait(monkeypatch):
    monkeypatch.setattr(settings, "rag_passage_max_chars", 600)
    block = build_context_block([_hit(SHADOW)], 800, "What is a shadow?")
    assert len(block) < 700


def test_shortening_the_top_passage_can_make_room_for_the_second(monkeypatch):
    """exp004's magnet poles: a 1,193-character exercise page left the
    233-character definition no room. Shortened, it fits at 1200 -- though
    not at 800, where 600 + 233 is still over."""
    monkeypatch.setattr(settings, "rag_passage_max_chars", 600)
    hits = [_hit("x" * 1193, 121), _hit("y" * 233, 117)]
    assert [h.page_start for h in prompt_hits(hits, "poles", 1200)] == [121, 117]
    assert [h.page_start for h in prompt_hits(hits, "poles", 800)] == [121]


# -- the same passage twice in a conversation --------------------------------

def test_a_passage_the_last_turn_sent_goes_out_again_verbatim(monkeypatch):
    monkeypatch.setattr(settings, "rag_passage_max_chars", 600)
    sent_before = "… exactly what the topic question was sent …"
    shown = prompt_hits([_hit(SHADOW, 7)], "How can we reduce it?", 800, {7: sent_before})
    assert shown[0].text == sent_before


def test_a_follow_up_on_the_same_passage_repeats_the_excerpt_block(monkeypatch):
    """The follow-up's prompt has to start with the topic turn's, excerpts and
    all, for the cache to cover it."""
    monkeypatch.setattr(settings, "rag_passage_max_chars", 600)

    async def fake_retrieve(store, question, **kwargs):
        return [_hit(SWEAT, 3)]

    monkeypatch.setattr(chat, "retrieve", fake_retrieve)
    session = Session("s1")
    topic_block, _, session.excerpts = asyncio.run(chat._retrieve_context(
        "Why does our skin sweat?", None, None, 800, session.excerpts))
    follow_block, _, _ = asyncio.run(chat._retrieve_context(
        "Does it do this in winter?", None, "Why does our skin sweat?", 800,
        session.excerpts))
    assert session.excerpts == {3: topic_block.split("\n", 1)[1]}
    assert follow_block == topic_block


def test_a_new_session_has_sent_nothing():
    assert Session("s1").excerpts == {}
