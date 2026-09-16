"""What the model re-reads between turns, and why it is shaped this way.

Only the student's questions are replayed; the answers they already have are
not, because the previous reply coming back in full cost ~3.9s of prefill on
every turn after the first. That leaves a hazard this module guards: with the
answers gone, two questions end up side by side, and two `user` messages in a
row are one request with two questions in it as far as a 1.5B model is
concerned. It answers both, oldest first.

Seen on a device before the separator existed -- "What is magnetic force?"
opened with "The Earth's rotation causes the position of the sun ... including
its length", which is the answer to the question before it, and signed off by
answering both in one sentence.

The separator is a fixed string rather than anything drawn from the reply. That
is deliberate: a constant keeps the prompt a strict extension of the previous
turn's, so Ollama's cache still covers it. The socratic nudge that used to sit
in this position changed every turn and could not be cached.
"""

from app.services.sessions import TURN_SEPARATOR, Session


def _session(*turns):
    s = Session("test")
    for role, text in turns:
        s.add(role, text)
    return s


Q1 = ("user", "Why does a shadow change length during the day?")
A1 = ("assistant", "Because the sun moves across the sky. [...long answer...]")
Q2 = ("user", "What is magnetic force?")


def test_two_questions_never_arrive_as_one_message():
    roles = [m["role"] for m in _session(Q1, A1, Q2).history(1)]
    assert roles == ["user", "assistant", "user"]


def test_the_separator_stands_in_for_the_answer():
    history = _session(Q1, A1, Q2).history(1)
    assert history[1] == {"role": "assistant", "content": TURN_SEPARATOR}
    assert A1[1] not in [m["content"] for m in history]


def test_the_separator_is_constant_across_turns():
    """A varying stub would break the shared prefix and cost more than it saves."""
    first = _session(Q1, A1, Q2).history(1)
    second = _session(
        ("user", "What is friction?"),
        ("assistant", "A force that opposes sliding. [...]"),
        ("user", "How do we reduce it?"),
    ).history(1)
    assert first[1]["content"] == second[1]["content"]


def test_the_questions_come_back_verbatim_and_in_order():
    history = _session(Q1, A1, Q2).history(1)
    assert [m["content"] for m in history if m["role"] == "user"] == [Q1[1], Q2[1]]


def test_a_single_question_needs_no_separator():
    assert _session(Q2).history(1) == [{"role": "user", "content": Q2[1]}]


def test_no_separator_when_the_window_replays_nothing():
    """questions=0 replays only the question being answered."""
    assert _session(Q1, A1, Q2).history(0) == [{"role": "user", "content": Q2[1]}]


def test_the_window_still_ends_on_the_student():
    """Whatever else is replayed, the model must be answering the last question."""
    history = _session(Q1, A1, Q2).history(1)
    assert history[-1] == {"role": "user", "content": Q2[1]}


def test_a_wider_window_separates_every_pair():
    history = _session(
        Q1, A1,
        ("user", "Does it work underwater?"),
        ("assistant", "Yes. [...]"),
        Q2,
    ).history(2)
    assert [m["role"] for m in history] == [
        "user", "assistant", "user", "assistant", "user"
    ]
    assert all(m["content"] == TURN_SEPARATOR
               for m in history if m["role"] == "assistant")


def test_empty_session_is_survivable():
    assert Session("test").history(1) == []
