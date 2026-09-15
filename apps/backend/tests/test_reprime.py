"""The background re-prime must rebuild exactly the next turn's prefix.

Its whole value is a cache checkpoint where the next question starts. Off by
one message -- the window sliding, the persona differing -- and the checkpoint
matches nothing and the student pays full price again, silently. These tests
pin the one rule that makes it line up: the next turn keeps the last
`max_history_messages` including its new question, so the prime is the last
limit-1 of what is stored when the answer finishes.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.routers import chat as chat_router  # noqa: E402
from app.schemas import TutorProfile  # noqa: E402
from app.services.sessions import store  # noqa: E402
from app.services.tutor import build_chat_messages  # noqa: E402


async def _prime_for(session, monkeypatch):
    # Off by default: the real 5s dispatch delay (see ollama_reprime_delay_
    # seconds) exists to keep re-prime off the CPU while the student is still
    # hearing the tail of the answer -- these tests are about the PROMPT it
    # builds and the task's own bookkeeping, not that delay, so it would only
    # make every test here slower for no coverage gained.
    monkeypatch.setattr(settings, "ollama_reprime_delay_seconds", 0.0)
    seen = []

    async def fake_prime(messages, model=None):
        seen.append(messages)
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router.client, "prime", fake_prime)
    chat_router._reprime_after_reply(session, None, None)
    for _ in range(20):
        if seen:
            break
        await asyncio.sleep(0)
    return seen


async def _session(turns):
    session = await store.create(TutorProfile(language="Hindi", level="Class 6"))
    for i in range(turns):
        session.add("user", "question {}".format(i))
        session.add("assistant", "answer {}".format(i))
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("turns", [1, 2, 5])  # window not full, exactly full, sliding
async def test_the_prime_is_the_next_turns_prompt_minus_its_question(turns, monkeypatch):
    monkeypatch.setattr(settings, "ollama_reprime_after_reply", True)
    monkeypatch.setattr(settings, "max_history_messages", 4)
    session = await _session(turns)

    seen = await _prime_for(session, monkeypatch)
    assert len(seen) == 1

    session.add("user", "the next question")
    next_turn = build_chat_messages(
        session.history(settings.max_history_messages), session.profile
    )
    assert seen[0] == next_turn[:-1]
    assert seen[0][-1]["role"] == "assistant"  # ends on the reply -> open turn


@pytest.mark.asyncio
async def test_switched_off_means_no_prime(monkeypatch):
    monkeypatch.setattr(settings, "ollama_reprime_after_reply", False)
    session = await _session(1)
    assert await _prime_for(session, monkeypatch) == []


@pytest.mark.asyncio
async def test_a_failed_prime_never_raises(monkeypatch):
    monkeypatch.setattr(settings, "ollama_reprime_after_reply", True)
    monkeypatch.setattr(settings, "ollama_reprime_delay_seconds", 0.0)
    session = await _session(1)

    async def broken(messages, model=None):
        raise RuntimeError("ollama went away")

    monkeypatch.setattr(chat_router.client, "prime", broken)
    chat_router._reprime_after_reply(session, None, None)
    for _ in range(20):
        if session.repriming is None:
            break
        await asyncio.sleep(0.01)  # the task swallowed and logged it; nothing to catch


@pytest.mark.asyncio
async def test_session_tracks_and_clears_its_own_repriming_task(monkeypatch):
    # Mirrors session.preparing's own lifecycle (see test_early_prime.py's
    # chat_prepare test): set at dispatch, cleared by the task's own
    # done-callback once it actually finishes -- not merely once .done() is
    # true synchronously, since done-callbacks run on a later tick.
    monkeypatch.setattr(settings, "ollama_reprime_after_reply", True)
    monkeypatch.setattr(settings, "ollama_reprime_delay_seconds", 0.0)
    session = await _session(1)

    async def slow_prime(messages, model=None):
        await asyncio.sleep(0.02)
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router.client, "prime", slow_prime)
    chat_router._reprime_after_reply(session, None, None)
    assert session.repriming is not None

    for _ in range(50):
        if session.repriming is None:
            break
        await asyncio.sleep(0.01)
    assert session.repriming is None


@pytest.mark.asyncio
async def test_the_delay_runs_before_prime_is_ever_called(monkeypatch):
    # 2026-09-15: re-prime used to fire client.prime() the instant decode
    # ended, colliding with the tail of TTS still speaking the answer (a
    # timestamped log caught one clip taking 13.5s instead of its usual <2s
    # because it overlapped a 7.5s re-prime call). This pins that the delay
    # is spent BEFORE prime() is touched at all -- not a delay tacked onto
    # the end -- and that cancelling during it means prime() is never called,
    # which is what makes this delay a genuine cancellation window rather
    # than just a later one.
    monkeypatch.setattr(settings, "ollama_reprime_after_reply", True)
    monkeypatch.setattr(settings, "ollama_reprime_delay_seconds", 10.0)
    session = await _session(1)

    called = False

    async def fake_prime(messages, model=None):
        nonlocal called
        called = True
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router.client, "prime", fake_prime)
    chat_router._reprime_after_reply(session, None, None)
    task = session.repriming
    assert task is not None

    for _ in range(5):
        await asyncio.sleep(0)
    assert called is False, "prime() must not be called until the delay elapses"

    task.cancel()
    for _ in range(10):
        if task.cancelled() or task.done():
            break
        await asyncio.sleep(0)
    assert task.cancelled()
    assert called is False, "cancelling during the delay must skip prime() entirely"


@pytest.mark.asyncio
async def test_a_new_real_question_cancels_a_still_running_reprime(monkeypatch):
    # Once a real question has arrived, that question IS the next turn --
    # it no longer needs the background re-prime of the PREVIOUS answer to
    # have finished, because it is about to read exactly that prefix itself.
    # A re-prime still running at that point only contends with the
    # question's own request to Ollama for the same 2 cores, so it must be
    # cancelled, unconditionally -- there is nothing to gain by waiting for
    # it the way an early-primed passage guess is worth waiting for.
    monkeypatch.setattr(settings, "ollama_reprime_after_reply", True)
    monkeypatch.setattr(settings, "ollama_reprime_delay_seconds", 0.0)
    monkeypatch.setattr(settings, "rag_early_prime_enabled", False)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)
    session = await _session(1)

    async def slow_prime(messages, model=None):
        await asyncio.sleep(5.0)
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router.client, "prime", slow_prime)
    chat_router._reprime_after_reply(session, None, None)
    still_running = session.repriming
    assert still_running is not None

    async def fake_retrieve(*a, **k):
        return []

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    await chat_router._retrieve_context("अगला सवाल", session.profile, session)

    for _ in range(10):
        if still_running.cancelled() or still_running.done():
            break
        await asyncio.sleep(0)
    assert still_running.cancelled()
