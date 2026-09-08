"""Where the textbook excerpts sit in the prompt, and why it is not negotiable.

Excerpts go at the front of the system message, above the persona. That looks
backwards for latency -- they are the only part of the prompt that changes each
turn, so putting them in messages[0] invalidates Ollama's KV cache from token
zero and the persona and the whole conversation are re-read on every turn, at
roughly 20ms per token on the target laptop.

Moving them next to the question was tried and measured. Against 12 pronoun
follow-ups ("why does it get bigger?", "does it work underwater?") across three
topics, with retrieval left exactly as it is:

    excerpts first, above the persona     11/12 answered from the conversation
    excerpts last, next to the question    5/12
    excerpts last, style rule restated     7/12

A pronoun-only follow-up embeds to nothing useful, so retrieval returns weakly
related chunks at distance 0.35-0.40 -- inside RAG_MAX_DISTANCE, so they reach
the prompt. Sitting next to the question they simply outweigh the dialogue and
the tutor answers about hens and cows instead. Front placement keeps them
subordinate to the conversation.

These tests exist to make that trade explicit rather than rediscovered. If the
retrieval side is fixed so follow-ups stop dragging in unrelated passages, the
reordering becomes worth revisiting -- rerun the follow-up comparison first.
"""

from app.schemas import TutorProfile
from app.services.tutor import build_chat_messages, build_system_prompt

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


def test_excerpts_sit_above_the_persona_and_the_style_rule():
    """Order inside that message matters as much as which message it is.

    The style rule has to stay last so it is the final instruction before the
    reply; the excerpts go above it, not between it and the answer.
    """
    system = build_chat_messages(HISTORY, PROFILE, CONTEXT)[0]["content"]
    assert system.index(CONTEXT) < system.index("You are a patient")
    assert system.index("You are a patient") < system.index("Most important rule:")


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
