"""The order of the prompt, and which parts of it are load-bearing.

One system message, built in three layers:

    1. persona and style rule
    2. the excerpt preamble ("use these, prefer their wording")
    3. the retrieved excerpts

then the conversation as its own turns after it.

The layer that is not negotiable is the last one: excerpts stay in the system
message and never attach to the question. That was measured. Against 12 pronoun
follow-ups ("why does it get bigger?", "does it work underwater?") across three
topics, with retrieval left exactly as it is:

    excerpts in the system message          11/12 answered from the conversation
    excerpts next to the question            5/12
    excerpts next to the question, rule restated  7/12

A pronoun-only follow-up embeds to nothing useful, so retrieval returns weakly
related chunks at distance 0.35-0.40 -- inside RAG_MAX_DISTANCE, so they reach
the prompt. Sitting next to the question they simply outweigh the dialogue and
the tutor answers about hens and cows instead.

Ordering *within* the system message is a softer call. Excerpts used to sit at
the very top, above the persona, because a wall of textbook in front of the
style rule pushed it out of reach and the model recited the passage instead of
tutoring from it. The rule is shorter now and the preamble frames the excerpts,
so they moved below it. If replies start reading like recitation, that trade is
the first place to look.
"""

from app.schemas import TutorProfile
from app.services.tutor import EXCERPT_PREAMBLE, build_chat_messages, build_system_prompt

CONTEXT = "[1] Class 6 Science - Light - p. 42\nLight travels in straight lines."
PROFILE = TutorProfile(subject="Science", level="Class 6")
HISTORY = [
    {"role": "user", "content": "What is light?"},
    {"role": "assistant", "content": "Light is what lets you see."},
    {"role": "user", "content": "Why does it get bigger?"},
]


def test_excerpts_go_in_the_system_message():
    messages = build_chat_messages(HISTORY, PROFILE, CONTEXT)
    assert messages[0]["role"] == "system"
    assert CONTEXT in messages[0]["content"]


def test_system_message_is_persona_then_preamble_then_excerpts():
    system = build_chat_messages(HISTORY, PROFILE, CONTEXT)[0]["content"]
    assert system.index("Patient tutor") < system.index("Most important rule:")
    assert system.index("Most important rule:") < system.index(EXCERPT_PREAMBLE)
    assert system.index(EXCERPT_PREAMBLE) < system.index(CONTEXT)


def test_persona_names_the_level_and_the_language():
    system = build_system_prompt(PROFILE)
    assert system.startswith("Patient tutor for a Class 6 student.")
    assert "Simple words, English, never invent facts." in system


def test_the_preamble_only_appears_with_excerpts():
    assert EXCERPT_PREAMBLE not in build_system_prompt(PROFILE)
    assert EXCERPT_PREAMBLE in build_system_prompt(PROFILE, CONTEXT)


def test_excerpts_never_attach_to_the_question():
    """The regression this guards: excerpts adjacent to the reply drown it out."""
    messages = build_chat_messages(HISTORY, PROFILE, CONTEXT)
    assert messages[-1] == {"role": "user", "content": "Why does it get bigger?"}
    assert all(CONTEXT not in m["content"] for m in messages[1:])


def test_history_is_passed_through_verbatim():
    assert build_chat_messages(HISTORY, PROFILE, CONTEXT)[1:] == HISTORY


def test_ungrounded_turn_carries_only_the_persona():
    assert build_chat_messages(HISTORY, PROFILE, None) == [
        {"role": "system", "content": build_system_prompt(PROFILE)}
    ] + HISTORY


def test_empty_history_is_survivable():
    assert build_chat_messages([], PROFILE, CONTEXT) == [
        {"role": "system", "content": build_system_prompt(PROFILE, CONTEXT)}
    ]
