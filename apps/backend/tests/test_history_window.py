"""What the model reads of the conversation, and why it is one message.

Only the student's questions ever went back, never the answers: the previous
reply coming back in full cost ~3.9s of prefill on every turn after the first.
Replaying those questions as chat turns then failed three ways, all seen live:

  1. Two student turns side by side are one request with two questions in it,
     and a 1.5B model answers both -- "What is magnetic force?" opened with
     "The Earth's rotation causes the position of the sun ... including its
     length", the answer to the question before it.

  2. A fixed "(answered)" assistant turn between them was copied: 7 of 12
     pronoun follow-ups came back as the single word "(answered)".

  3. The opening sentence of the real answer in that slot was copied for
     length: 6 of 6 topic switches came back as one sentence.

So the model gets one student message and no assistant turn at all. A question
that names its own topic goes as asked; a follow-up that leans on the one before
it ("How can we reduce it?", "Why?") goes with that question named as background
and the style rule's length spelled out again, last.
"""

from app.config import settings
from app.schemas import TutorProfile
from app.services.sessions import Session
from app.services.tutor import (
    FOLLOW_UP_PROMPT,
    FOLLOW_UP_RULES,
    STYLE_RULES,
    build_system_prompt,
    follow_up_message,
)


def _session(*turns):
    s = Session("test")
    for role, text in turns:
        s.add(role, text)
    return s


Q1 = ("user", "What is frictional force?")
A1 = ("assistant", "Frictional force is the force that opposes motion between two surfaces. "
                   "It acts against the direction of motion. [...a long explanation...]")
FOLLOW_UP = ("user", "How can we reduce it?")
NEW_TOPIC = ("user", "What is magnetic force?")


# --------------------------------------------------------------------------
# a question that names its own topic carries nothing
# --------------------------------------------------------------------------
def test_a_new_topic_is_sent_as_asked_with_no_earlier_turn():
    """The double-answer and the one-sentence reply both came from the earlier
    turn being there at all."""
    assert _session(Q1, A1, NEW_TOPIC).history(1) == [
        {"role": "user", "content": NEW_TOPIC[1]}
    ]


def test_a_first_question_is_just_the_question():
    assert _session(Q1).history(1) == [{"role": "user", "content": Q1[1]}]


def test_a_pronoun_with_nothing_before_it_is_just_the_question():
    assert _session(FOLLOW_UP).history(1) == [{"role": "user", "content": FOLLOW_UP[1]}]


# --------------------------------------------------------------------------
# a follow-up is one message with the earlier question as background
# --------------------------------------------------------------------------
def test_a_follow_up_is_one_student_message():
    history = _session(Q1, A1, FOLLOW_UP).history(1)
    assert [m["role"] for m in history] == ["user"]


def test_a_follow_up_names_the_earlier_question_and_asks_its_own_verbatim():
    content = _session(Q1, A1, FOLLOW_UP).history(1)[0]["content"]
    assert content == follow_up_message([Q1[1]], FOLLOW_UP[1])
    assert '"What is frictional force?"' in content
    assert "How can we reduce it?" in content
    assert content.index(Q1[1]) < content.index(FOLLOW_UP[1])


def test_a_follow_up_ends_on_the_rule_spelled_out():
    """Last, because the model weights the end of the prompt most. Spelled out,
    because naming the rule alone left 15 of 20 follow-ups at one sentence."""
    content = _session(Q1, A1, FOLLOW_UP).history(1)[0]["content"]
    assert content.endswith("most important rule: " + FOLLOW_UP_RULES["socratic"])
    assert "Answer only the follow-up question" in content


def test_the_rule_spelled_out_follows_the_session_style():
    session = _session(Q1, A1, FOLLOW_UP)
    session.profile = TutorProfile(style="exam_prep")
    assert session.history(1)[0]["content"].endswith(FOLLOW_UP_RULES["exam_prep"])


def test_no_answer_text_is_ever_replayed():
    """Not the body (3.9s of prefill), and not the opening (copied for length)."""
    for current in (FOLLOW_UP, NEW_TOPIC):
        text = " ".join(m["content"] for m in _session(Q1, A1, current).history(1))
        assert "opposes motion" not in text
        assert "long explanation" not in text


def test_no_assistant_turn_is_ever_sent():
    """A fixed stub and a real opening were both copied."""
    session = _session(Q1, A1, ("user", "Does it help us walk?"),
                       ("assistant", "Yes, friction lets our shoes grip the ground."),
                       FOLLOW_UP)
    for n in (0, 1, 2, 5):
        assert all(m["role"] == "user" for m in session.history(n))


def test_questions_zero_carries_nothing_even_for_a_follow_up():
    assert _session(Q1, A1, FOLLOW_UP).history(0) == [
        {"role": "user", "content": FOLLOW_UP[1]}
    ]


def test_a_wider_window_names_earlier_questions_oldest_first():
    session = _session(Q1, A1, ("user", "Does it help us walk?"),
                       ("assistant", "Yes, friction lets our shoes grip the ground."),
                       FOLLOW_UP)
    assert session.earlier_questions(2) == [Q1[1], "Does it help us walk?"]
    assert session.history(2)[0]["content"] == follow_up_message(
        [Q1[1], "Does it help us walk?"], FOLLOW_UP[1])
    assert session.earlier_questions(1) == ["Does it help us walk?"]


def test_the_window_never_reaches_past_the_start():
    assert _session(Q1, A1, FOLLOW_UP).earlier_questions(5) == [Q1[1]]


def test_an_unanswered_earlier_question_is_still_background():
    """Only reachable if a failed turn was not rolled back. It is named as
    background inside one message, so it cannot read as a second request."""
    history = _session(Q1, FOLLOW_UP).history(1)
    assert [m["role"] for m in history] == ["user"]
    assert Q1[1] in history[0]["content"]


def test_earlier_questions_is_empty_for_a_new_topic():
    """This is what the turn log records as history_msgs."""
    assert _session(Q1, A1, NEW_TOPIC).earlier_questions(1) == []
    assert _session(Q1, A1, FOLLOW_UP).earlier_questions(1) == [Q1[1]]


def test_empty_session_is_survivable():
    assert Session("test").history(1) == []
    assert Session("test").earlier_questions(1) == []


# --------------------------------------------------------------------------
# the message itself
# --------------------------------------------------------------------------
def test_follow_up_message_strips_and_joins_earlier_questions():
    assert follow_up_message(["  What is a lever? "], " Where is its fulcrum? ") == (
        'My earlier question was: "What is a lever?"\n'
        "My follow-up question: Where is its fulcrum?\n"
        "Answer only the follow-up question, and strictly follow the most "
        "important rule: 5 to 6 plain sentences, with one everyday example."
    )
    assert '"A?", then "B?"' in follow_up_message(["A?", "B?"], "C it?")


def test_an_unknown_style_falls_back_to_socratic_like_the_system_prompt():
    assert follow_up_message(["A?"], "B it?", "nonsense").endswith(FOLLOW_UP_RULES["socratic"])


def test_every_style_has_a_follow_up_rule():
    assert set(FOLLOW_UP_RULES) == set(STYLE_RULES)


def test_the_rule_it_points_at_exists_in_the_system_prompt():
    """The follow-up calls it "the most important rule", so that name must be
    what build_system_prompt actually writes, for every style."""
    assert "most important rule" in FOLLOW_UP_PROMPT
    for style in STYLE_RULES:
        assert "Most important rule:" in build_system_prompt(TutorProfile(style=style))


def test_the_socratic_follow_up_rule_agrees_with_the_style_rule():
    """A follow-up must not be held to a different length than a first question."""
    assert "5 to 6 plain sentences" in STYLE_RULES["socratic"]
    assert FOLLOW_UP_RULES["socratic"].startswith("5 to 6 plain sentences")


# --------------------------------------------------------------------------
# settings.force_follow_up_prompt (testing-only override)
# --------------------------------------------------------------------------
def test_force_follow_up_prompt_treats_a_new_topic_as_a_follow_up(monkeypatch):
    """With the override on, even a question that names its own topic is sent
    in the follow-up shape, as long as there is an earlier question to carry."""
    monkeypatch.setattr(settings, "force_follow_up_prompt", True)
    assert _session(Q1, A1, NEW_TOPIC).earlier_questions(1) == [Q1[1]]
    assert _session(Q1, A1, NEW_TOPIC).history(1) == [
        {"role": "user", "content": follow_up_message([Q1[1]], NEW_TOPIC[1])}
    ]


def test_force_follow_up_prompt_still_carries_nothing_with_no_earlier_question(monkeypatch):
    monkeypatch.setattr(settings, "force_follow_up_prompt", True)
    assert Session("test").earlier_questions(1) == []
    assert _session(Q1).earlier_questions(1) == []


def test_force_follow_up_prompt_off_by_default():
    assert settings.force_follow_up_prompt is False
