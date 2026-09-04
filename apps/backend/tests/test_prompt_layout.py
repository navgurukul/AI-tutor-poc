"""Where the excerpts sit in the prompt, and why moving them costs 8x.

This file exists because the obvious optimisation is wrong, and it is wrong in
a way no amount of reading can show you.

The reasoning that fails: retrieved excerpts sit at the FRONT of the system
prompt and change on every question, so they must be invalidating the model's
cached prefix and forcing the persona and the whole replayed history to be
re-read every turn. Move them onto the last user message, keep the stable
persona in front, and the prefix should survive.

It was built and measured. Same three questions, same session:

    excerpts at the front   11,255 -> 11,647 -> 15,975 ms of prefill
    excerpts moved down     11,093 -> 11,507 -> 15,950 ms

Nothing. And on a repeated question -- where retrieval returns the same
passages, so the prompt really is unchanged up to the new turn:

    excerpts at the front   14,274 ms -> 1,631 ms   (8.8x faster)
    excerpts moved down     14,274 ms -> 13,625 ms  (no reuse at all)

The cache does not reuse a shared prefix. It reuses a prompt that STRICTLY
EXTENDS the last one -- turn N's entire prompt has to be a prefix of turn
N+1's. Excerpts in the system message satisfy that whenever two consecutive
questions retrieve the same passages, which is the normal case for a follow-up
on one topic. Excerpts on the last user message can NEVER satisfy it: turn N
sends "excerpts + question" in that slot and turn N+1 replays a bare
"question" there, so the two sequences always diverge.

So the excerpts stay where they are, and the way to earn more reuse is to make
retrieval return the same passages more often -- not to move them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import TutorProfile  # noqa: E402
from app.services.tutor import build_chat_messages, build_system_prompt  # noqa: E402

CONTEXT_A = (
    "Here are excerpts from the student's own textbook.\n\n"
    "[1] NCERT Science (Class 9) - 3.2.3 HOW DO ATOMS EXIST? - p. 35\n"
    "Atoms of most elements are not able to exist independently."
)
CONTEXT_B = CONTEXT_A.replace("3.2.3 HOW DO ATOMS EXIST?", "4.2 The Structure of an Atom")

EN = TutorProfile(subject="Science", level="Class 9", language="English", style="teach")


def _flatten(messages):
    """The prompt as the model sees it: one string, in order."""
    return "\n".join("{}:{}".format(m["role"], m["content"]) for m in messages)


def _turn(exchanges, question, context):
    """The messages for one turn, given the completed exchanges before it."""
    history = list(exchanges) + [{"role": "user", "content": question}]
    return build_chat_messages(history, EN, context)


# -- the property that buys the reuse --------------------------------------

def test_a_follow_up_strictly_extends_the_previous_prompt():
    """The whole cache win, in one assertion.

    Retrieval returned the same passages for both turns, so turn 1's entire
    prompt must still be a prefix of turn 2's. Measured payoff when it holds:
    14,274 ms of prefill falls to 1,631 ms.
    """
    turn1 = _turn([], "What is an atom?", CONTEXT_A)
    turn2 = _turn(
        [
            {"role": "user", "content": "What is an atom?"},
            {"role": "assistant", "content": "An atom is the smallest particle."},
        ],
        "What is an atom?",
        CONTEXT_A,
    )
    assert _flatten(turn2).startswith(_flatten(turn1)), (
        "turn 2 no longer extends turn 1 -- the prompt cache is lost"
    )


def test_the_excerpts_are_what_breaks_the_extension_when_they_change():
    """The cost side, pinned so the win above is not read as unconditional.

    Different passages mean a different system message, which means no reuse
    and a full ~11 ms/token prefill. This is the case worth attacking -- by
    retrieving the same passages more often, not by moving them.
    """
    turn1 = _turn([], "What is an atom?", CONTEXT_A)
    turn2 = _turn(
        [
            {"role": "user", "content": "What is an atom?"},
            {"role": "assistant", "content": "An atom is the smallest particle."},
        ],
        "How do atoms exist?",
        CONTEXT_B,
    )
    assert not _flatten(turn2).startswith(_flatten(turn1))


# -- placement -------------------------------------------------------------

def test_the_excerpts_live_in_the_system_message():
    """Moving them onto the last user message was built, measured and reverted:
    it makes a strict extension structurally impossible, because turn N sends
    "excerpts + question" where turn N+1 replays a bare "question"."""
    messages = build_chat_messages(
        [{"role": "user", "content": "How do atoms exist?"}], EN, CONTEXT_A
    )
    assert "NCERT" in messages[0]["content"], "excerpts belong in the system message"
    assert messages[-1]["content"] == "How do atoms exist?", (
        "the last user message must stay the bare question -- anything appended "
        "to it is replayed differently next turn and breaks the extension"
    )


def test_the_history_is_replayed_untouched():
    history = [
        {"role": "user", "content": "What is an atom?"},
        {"role": "assistant", "content": "An atom is the smallest particle."},
        {"role": "user", "content": "How do they exist?"},
    ]
    snapshot = [dict(m) for m in history]
    assert build_chat_messages(history, EN, CONTEXT_A)[1:] == history
    assert history == snapshot, "the stored session must not be mutated"


def test_an_unaided_turn_carries_no_excerpt_scaffolding():
    history = [{"role": "user", "content": "Who painted the Mona Lisa?"}]
    for empty in (None, ""):
        messages = build_chat_messages(history, EN, empty)
        assert messages[1:] == history
        assert messages[0]["content"] == build_system_prompt(EN, empty)


# -- the quality rule the placement protects -------------------------------

def test_the_style_rule_stays_at_the_end_of_the_system_prompt():
    """The other reason the excerpts sit in front: this model follows whatever
    it read last, and a few hundred words of textbook dropped after the persona
    pushed the style rules out of reach -- it started reciting the passage
    instead of tutoring from it."""
    system = build_chat_messages(
        [{"role": "user", "content": "q"}], EN, CONTEXT_A
    )[0]["content"]
    assert system.index("NCERT") < system.index("Most important rule:")
    assert system.rstrip().endswith("never pad it out past three sentences.")


def test_the_script_instruction_outlives_the_style_rule_in_hindi():
    """An English reply to a Hindi student is the wrong answer, not a degraded
    one, so the script rule is placed after the style rule -- last wins."""
    hindi = TutorProfile(level="Class 9", language="Hindi", style="teach")
    system = build_system_prompt(hindi, CONTEXT_A)
    assert system.index("Most important rule:") < system.index("Write your ENTIRE reply in Hindi")
