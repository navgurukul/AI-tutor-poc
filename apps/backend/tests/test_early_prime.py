"""Early priming: read a question's passage into the cache before Send.

The whole feature rests on one guarantee -- the messages `_prepare_passage`
primes must be an EXACT prefix of what the real ask sends, or Ollama's
checkpoint matches nothing and the "prepared" turn is no faster than an
unprimed one. These tests pin that prefix match (parametrized over how full
the history window is, the same way test_reprime.py pins the re-prime's),
`Session.claim_prepared`'s three ways to say no, and that a miss always falls
back to exactly today's single-message turn -- never a broken one.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.routers import chat as chat_router  # noqa: E402
from app.schemas import TutorProfile  # noqa: E402
from app.services.rag.store import Retrieved  # noqa: E402
from app.services.sessions import PreparedPassage, store  # noqa: E402
from app.services.tutor import build_chat_messages, build_passage_ack, build_turn_message  # noqa: E402


def _hit(cid, text=None):
    return Retrieved(
        chunk_id=cid, text=text or ("passage %d" % cid), heading="", page_start=1,
        page_end=1, distance=0.3, document_title="t", grade=6, subject="s",
        language="Hindi",
    )


async def _session(turns=0):
    session = await store.create(TutorProfile(language="Hindi", level="Class 6", subject="s"))
    for i in range(turns):
        session.add("user", "question {}".format(i))
        session.add("assistant", "answer {}".format(i))
    return session


# --------------------------------------------------------------------------
# Session.claim_prepared / pop_last -- pure, no I/O
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claim_matches_and_clears():
    session = await _session()
    session.prepared = PreparedPassage(chunk_ids=[1, 2], block="B", ack="A", history_len=0)
    claimed = session.claim_prepared([1, 2])
    assert claimed is not None and claimed.block == "B"
    assert session.prepared is None


@pytest.mark.asyncio
async def test_claim_rejects_different_passages():
    session = await _session()
    session.prepared = PreparedPassage(chunk_ids=[1, 2], block="B", ack="A", history_len=0)
    assert session.claim_prepared([1, 3]) is None
    assert session.prepared is None  # a rejected guess is not kept for later


@pytest.mark.asyncio
async def test_claim_rejects_stale_history():
    session = await _session()
    session.prepared = PreparedPassage(chunk_ids=[1, 2], block="B", ack="A", history_len=0)
    session.add("user", "something happened while the prime was in flight")
    assert session.claim_prepared([1, 2]) is None


@pytest.mark.asyncio
async def test_claim_on_nothing_prepared_is_a_quiet_miss():
    session = await _session()
    assert session.claim_prepared([1, 2]) is None


def test_pop_last_removes_exactly_count():
    import asyncio as _asyncio

    async def run():
        session = await _session()
        session.add("user", "passage")
        session.add("assistant", "ack")
        session.add("user", "question")
        session.pop_last(3)
        assert session.messages == []
        session.add("user", "x")
        session.pop_last(5)  # over-count must not raise
        assert session.messages == []

    _asyncio.run(run())


# --------------------------------------------------------------------------
# The prefix match: what _prepare_passage primes vs. what a real ask sends
# --------------------------------------------------------------------------

async def _prepared_for(session, hits, monkeypatch):
    """Run _prepare_passage with retrieval and Ollama mocked, return the
    exact messages it primed (or None if it declined to prime at all)."""
    async def fake_retrieve(*a, **k):
        return hits

    seen = []

    async def fake_prime(messages, model=None):
        seen.append(messages)
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_router.client, "prime", fake_prime)
    await chat_router._prepare_passage(session, "काली मृदा क्या होती है")
    return seen[0] if seen else None


@pytest.mark.asyncio
@pytest.mark.parametrize("turns", [0, 1, 2, 5])  # window not full, exactly full, sliding
async def test_primed_messages_are_an_exact_prefix_of_the_real_ask(turns, monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "max_history_messages", 6)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)
    session = await _session(turns)
    hits = [_hit(101), _hit(102)]

    primed = await _prepared_for(session, hits, monkeypatch)
    assert primed is not None
    assert session.prepared is not None
    prepared = session.prepared

    # Simulate the real ask claiming it: the SAME three messages _append_turn
    # would add (passage, ack, question), then the history window a real turn
    # would actually send.
    claimed = session.claim_prepared(prepared.chunk_ids)
    assert claimed is not None
    session.add("user", claimed.block)
    session.add("assistant", claimed.ack)
    session.add("user", "काली मृदा क्या होती है\n\nReply only in Hindi (Devanagari).")
    real_ask = build_chat_messages(
        session.history(settings.max_history_messages), session.profile
    )
    # The prime ends right after the acknowledgement -- everything up to and
    # including it must be byte-identical to what the real ask sends, so
    # Ollama resumes from exactly that checkpoint instead of re-reading it.
    assert primed == real_ask[:-1]
    assert primed[-1]["role"] == "assistant"  # ends on the ack -> open turn


@pytest.mark.asyncio
async def test_declines_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", False)
    session = await _session()
    primed = await _prepared_for(session, [_hit(1)], monkeypatch)
    assert primed is None
    assert session.prepared is None


@pytest.mark.asyncio
async def test_declines_on_empty_draft(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    session = await _session()
    seen = []

    async def must_not_run(*a, **k):
        seen.append(True)
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router.client, "prime", must_not_run)
    await chat_router._prepare_passage(session, "   ")
    assert not seen


@pytest.mark.asyncio
async def test_declines_when_pinned(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(chat_router, "_is_pinned", lambda profile: True)
    session = await _session()
    primed = await _prepared_for(session, [_hit(1)], monkeypatch)
    assert primed is None  # the corpus is already the cached system prompt


@pytest.mark.asyncio
async def test_declines_on_a_followup(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "rag_followup_reuse", True)
    session = await _session()
    session.last_hit_ids = [7]
    seen = []

    async def must_not_run(*a, **k):
        seen.append(True)
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router.client, "prime", must_not_run)
    await chat_router._prepare_passage(session, "इसका एक उदाहरण दीजिए")
    assert not seen  # a follow-up reuses the last passage for free


@pytest.mark.asyncio
async def test_a_newer_prepare_wins_over_a_slower_older_one(monkeypatch):
    """Two drafts in flight at once, finishing out of order: the result that
    lands must be for the MOST RECENTLY DISPATCHED draft, not whichever
    happened to finish first."""
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)
    session = await _session()

    calls = []

    async def fake_retrieve(_store, message, **k):
        calls.append(message)
        return [_hit(1)] if message == "first draft" else [_hit(2)]

    async def fake_prime(messages, model=None):
        # The SECOND call (the newer draft) resolves first.
        if len(calls) == 1:
            await asyncio.sleep(0.02)
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_router.client, "prime", fake_prime)

    first = asyncio.create_task(chat_router._prepare_passage(session, "first draft"))
    await asyncio.sleep(0)  # let it dispatch and start "retrieving"
    second = asyncio.create_task(chat_router._prepare_passage(session, "second draft"))
    await asyncio.gather(first, second)

    assert session.prepared is not None
    assert session.prepared.chunk_ids == [2]  # the newer draft's passage, not the older one's


@pytest.mark.asyncio
async def test_already_seen_passages_are_not_reprimed(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)
    session = await _session()
    session.context_chunk_ids = [101, 102]  # already pasted earlier this session
    primed = await _prepared_for(session, [_hit(101), _hit(102)], monkeypatch)
    assert primed is None
    assert session.prepared is None


# --------------------------------------------------------------------------
# _retrieve_context: claiming (and missing) a prepared passage
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_context_claims_a_matching_prepared_passage(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "metrics_enabled", True)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1), _hit(2)]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()
    session.prepared = PreparedPassage(
        chunk_ids=[1, 2], block="PRIMED BLOCK", ack="ठीक है.", history_len=len(session.messages),
    )

    rc = await chat_router._retrieve_context("किसी भी सवाल", session.profile, session)
    assert rc.primed is not None
    assert rc.primed.block == "PRIMED BLOCK"
    assert rc.context is None  # nothing left to inline -- it is a turn back
    assert rc.trace is not None and rc.trace.primed is True
    assert [h.chunk_id for h in rc.hits] == [1, 2]


@pytest.mark.asyncio
async def test_retrieve_context_falls_back_when_the_guess_missed(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(9)]  # not what was prepared

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()
    session.prepared = PreparedPassage(
        chunk_ids=[1, 2], block="PRIMED BLOCK", ack="ठीक है.", history_len=len(session.messages),
    )

    rc = await chat_router._retrieve_context("a different question", session.profile, session)
    assert rc.primed is None
    assert rc.context is not None and "passage 9" in rc.context  # inlined normally
    assert session.prepared is None  # the miss still consumed the stale guess


@pytest.mark.asyncio
async def test_retrieve_context_ignores_a_prepared_passage_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", False)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1), _hit(2)]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()
    session.prepared = PreparedPassage(
        chunk_ids=[1, 2], block="PRIMED BLOCK", ack="ठीक है.", history_len=len(session.messages),
    )

    rc = await chat_router._retrieve_context("किसी भी सवाल", session.profile, session)
    assert rc.primed is None
    assert rc.context is not None  # the single-message layout, unchanged
    assert session.prepared is not None  # untouched -- the setting was never consulted


# --------------------------------------------------------------------------
# rag_fallback_max_passages: a miss pastes less, but never forgets the rest
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prepare_uses_the_bigger_prime_cap_not_the_fallback_cap(monkeypatch):
    # A caught guess was already read for free -- there is no latency reason
    # to keep it as small as a miss, which pays per token at Send. Long text
    # (many trigrams) trimmed to the SMALL cap (rag_passage_token_cap) would
    # cut well short of what the BIG cap (rag_prime_passage_token_cap) keeps.
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "rag_passage_token_cap", 10)
    monkeypatch.setattr(settings, "rag_prime_passage_token_cap", 200)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    # Real danda-terminated sentences -- trim_passage cannot partially trim a
    # single run-on "sentence" with no split points, so the fake text needs
    # real sentence boundaries for either cap to actually do anything.
    long_text = "".join("यह वाक्य संख्या {} है।".format(i) for i in range(60))

    async def fake_retrieve(*a, **k):
        return [_hit(1, long_text)]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)

    async def fake_prime(messages, model=None):
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router.client, "prime", fake_prime)
    session = await _session()
    await chat_router._prepare_passage(session, "सवाल")

    assert session.prepared is not None
    primed_len = len(session.prepared.block)

    # A separate session's MISS, same source text, must trim to the small cap.
    session2 = await _session()
    monkeypatch.setattr(settings, "rag_early_prime_enabled", False)
    rc = await chat_router._retrieve_context("सवाल", session2.profile, session2)
    assert rc.context is not None
    assert len(rc.context) < primed_len, "a miss must paste less than a caught guess gets to keep"


@pytest.mark.asyncio
async def test_a_miss_pastes_only_the_capped_count(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", False)
    monkeypatch.setattr(settings, "rag_fallback_max_passages", 1)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1, "first"), _hit(2, "second"), _hit(3, "third")]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()

    rc = await chat_router._retrieve_context("सवाल", session.profile, session)
    assert "first" in rc.context and "second" not in rc.context and "third" not in rc.context
    # hits/citations stay whole -- only what got PASTED shrank.
    assert [h.chunk_id for h in rc.hits] == [1, 2, 3]


@pytest.mark.asyncio
async def test_zero_cap_means_paste_everything_a_miss_retrieved(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", False)
    monkeypatch.setattr(settings, "rag_fallback_max_passages", 0)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1, "first"), _hit(2, "second")]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()

    rc = await chat_router._retrieve_context("सवाल", session.profile, session)
    assert "first" in rc.context and "second" in rc.context


@pytest.mark.asyncio
async def test_a_passage_dropped_by_the_cap_is_not_marked_seen(monkeypatch):
    """The bug this whole section guards against: capping what gets PASTED
    must not also mark the dropped passage as already shown, or a later turn
    would withhold it forever on a topic the model was never actually given."""
    monkeypatch.setattr(settings, "rag_early_prime_enabled", False)
    monkeypatch.setattr(settings, "rag_fallback_max_passages", 1)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1, "first"), _hit(2, "second")]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()

    rc1 = await chat_router._retrieve_context("सवाल", session.profile, session)
    assert "first" in rc1.context and "second" not in rc1.context
    assert session.context_chunk_ids == [1], "only the PASTED chunk is remembered"

    # A later turn that retrieves the SAME two chunks must still be able to
    # paste the one that was dropped last time -- it was never actually shown.
    rc2 = await chat_router._retrieve_context("सवाल फिर से", session.profile, session)
    assert "second" in rc2.context
    assert "first" not in rc2.context  # THIS one is now the already-seen one


@pytest.mark.asyncio
async def test_a_primed_turn_remembers_every_passage_it_actually_showed(monkeypatch):
    """The primed path is exempt from the cap -- both passages are free once
    caught -- so both must be marked seen, not just the first."""
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "rag_fallback_max_passages", 1)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1), _hit(2)]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()
    session.prepared = PreparedPassage(
        chunk_ids=[1, 2], block="PRIMED", ack="ठीक है.", history_len=len(session.messages),
    )

    rc = await chat_router._retrieve_context("सवाल", session.profile, session)
    assert rc.primed is not None
    assert session.context_chunk_ids == [1, 2]


# --------------------------------------------------------------------------
# _append_turn: history gets the right shape either way
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_append_turn_adds_three_messages_when_primed():
    session = await _session()
    rc = chat_router.RetrievedContext(
        context=None, sources=[], hits=[], trace=None,
        primed=PreparedPassage(chunk_ids=[1], block="PASSAGE", ack="ठीक है.", history_len=0),
    )
    chat_router._append_turn(session, rc, "सवाल", pinned=False)
    assert [m.content for m in session.messages] == [
        "PASSAGE", "ठीक है.",
        build_turn_message("सवाल", session.profile, None, grounded=True),
    ]
    assert [m.role for m in session.messages] == ["user", "assistant", "user"]


@pytest.mark.asyncio
async def test_append_turn_adds_one_message_when_not_primed():
    session = await _session()
    rc = chat_router.RetrievedContext(context="PASSAGE", sources=[], hits=[], trace=None)
    chat_router._append_turn(session, rc, "सवाल", pinned=False)
    assert len(session.messages) == 1
    assert session.messages[0].role == "user"
    assert session.messages[0].content.startswith("PASSAGE")


# --------------------------------------------------------------------------
# tutor.build_passage_ack
# --------------------------------------------------------------------------

@pytest.mark.parametrize("language,expected", [
    ("Hindi", "ठीक है."),
    ("hindi", "ठीक है."),  # case-insensitive, matches every other language check in tutor.py
    ("Marathi", "ठीक आहे."),
    ("English", "Understood."),
    (None, "Understood."),
])
def test_build_passage_ack_is_language_aware(language, expected):
    profile = TutorProfile(language=language) if language else None
    assert build_passage_ack(profile) == expected


def test_the_ack_is_fixed_not_derived_from_the_question():
    # Fixed on purpose: it is replayed on every later turn, so it has to be
    # byte-identical every time or it forks the cached prefix -- see the
    # function's own docstring. Calling it twice must return the same string.
    profile = TutorProfile(language="Hindi")
    assert build_passage_ack(profile) == build_passage_ack(profile)


# --------------------------------------------------------------------------
# Waiting a bounded moment for a prepare that is still in flight
# --------------------------------------------------------------------------

async def _delayed_prepare(session, delay, chunk_ids, block="PRIMED", ack="ठीक है."):
    """Stand-in for the real background task: after `delay`, writes a
    PreparedPassage the way _prepare_passage would on success."""
    await asyncio.sleep(delay)
    session.prepared = PreparedPassage(
        chunk_ids=chunk_ids, block=block, ack=ack, history_len=len(session.messages),
    )


@pytest.mark.asyncio
async def test_waits_for_an_in_flight_prepare_that_finishes_in_time(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "rag_early_prime_wait_seconds", 1.0)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1), _hit(2)]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()
    session.preparing = asyncio.create_task(_delayed_prepare(session, 0.05, [1, 2]))

    started = asyncio.get_event_loop().time()
    rc = await chat_router._retrieve_context("प्रश्न", session.profile, session)
    elapsed = asyncio.get_event_loop().time() - started

    assert rc.primed is not None
    assert rc.primed.block == "PRIMED"
    if rc.trace is not None:
        assert rc.trace.primed is True
    assert elapsed < 1.0, "must not wait the full budget once the guess actually lands"


@pytest.mark.asyncio
async def test_gives_up_after_the_budget_if_the_prepare_is_too_slow(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "rag_early_prime_wait_seconds", 0.1)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1), _hit(2)]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()
    slow = asyncio.create_task(_delayed_prepare(session, 5.0, [1, 2]))
    session.preparing = slow

    started = asyncio.get_event_loop().time()
    rc = await chat_router._retrieve_context("प्रश्न", session.profile, session)
    elapsed = asyncio.get_event_loop().time() - started

    assert rc.primed is None
    assert rc.context is not None  # fell back to the normal pasted-inline turn
    assert elapsed < 1.0, "must give up at the budget, not wait for the slow prepare"

    # Cancelled once given up on, not left running: 2026-09-14, letting it
    # keep going was measured to still slow the turn down even with the wait
    # itself off -- Ollama serialises gemma2 access, so a still-running
    # prepare contends with this turn's own prefill regardless of whether
    # anything here is waiting for it. Cancellation is cooperative (a
    # request, not immediate), so give the loop a couple of ticks.
    for _ in range(10):
        if slow.cancelled() or slow.done():
            break
        await asyncio.sleep(0)
    assert slow.cancelled()


@pytest.mark.asyncio
async def test_waiting_for_the_wrong_guess_still_falls_back_cleanly(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "rag_early_prime_wait_seconds", 1.0)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1), _hit(2)]  # the REAL question's passages

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()
    # The in-flight prepare is for a DIFFERENT draft -- lands, but doesn't match.
    session.preparing = asyncio.create_task(_delayed_prepare(session, 0.05, [9, 9]))

    rc = await chat_router._retrieve_context("प्रश्न", session.profile, session)
    assert rc.primed is None
    assert rc.context is not None
    # rag_fallback_max_passages (default 1): a miss pastes fewer than it
    # retrieved. Both still count toward citations/groundedness via rc.hits.
    assert "passage 1" in rc.context and "passage 2" not in rc.context
    assert [h.chunk_id for h in rc.hits] == [1, 2]


@pytest.mark.asyncio
async def test_no_wait_when_nothing_is_preparing(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "rag_early_prime_wait_seconds", 4.0)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1), _hit(2)]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()
    assert session.preparing is None

    started = asyncio.get_event_loop().time()
    rc = await chat_router._retrieve_context("प्रश्न", session.profile, session)
    elapsed = asyncio.get_event_loop().time() - started

    assert rc.primed is None
    assert elapsed < 0.5, "no prepare in flight -- must not wait at all"


@pytest.mark.asyncio
async def test_default_wait_budget_lets_a_fast_prepare_land(monkeypatch):
    # Regression guard for 2026-09-14: the wait defaulted on (4.0), then off
    # (0.0) the same day once real usage showed it cost more than it saved --
    # because back then the wait ran AFTER this turn's own retrieve() had
    # already started, so the wait and the ask's own embed call contended
    # with the still-running prepare's embed call at the same time.
    #
    # RE-ENABLED at a small default (0.35) once the wait was moved to run
    # BEFORE retrieve() (see _retrieve_context), where it cannot contend with
    # anything else this turn does. This pins that new default, and that at
    # this default a prepare which lands well within budget is still caught.
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)
    assert settings.rag_early_prime_wait_seconds == 0.35

    async def fake_retrieve(*a, **k):
        return [_hit(1), _hit(2)]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()
    session.preparing = asyncio.create_task(_delayed_prepare(session, 0.05, [1, 2]))

    started = asyncio.get_event_loop().time()
    rc = await chat_router._retrieve_context("प्रश्न", session.profile, session)
    elapsed = asyncio.get_event_loop().time() - started

    assert rc.primed is not None
    assert elapsed < 0.35, "must not wait the full budget once the guess actually lands"


@pytest.mark.asyncio
async def test_the_wait_and_cancel_happen_before_this_turns_own_retrieval_not_after(monkeypatch):
    # The ordering fix, 2026-09-14: waiting (or cancelling) only after a miss
    # was decided let this turn's own retrieve() run concurrently with (and
    # contend against) the prepare's -- both call the same embedding model.
    # This pins that by the time retrieve() is actually invoked, a prepare
    # too slow to land within the grace period has ALREADY been cancelled,
    # not merely eligible for cancellation later.
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    session = await _session()
    slow = asyncio.create_task(_delayed_prepare(session, 5.0, [9, 9]))
    session.preparing = slow

    seen_state_at_call_time = {}

    async def fake_retrieve(*a, **k):
        # A cancellation is a request, not instant -- cancelled() only
        # becomes true once the task has actually processed it. What must
        # already be true HERE, before this function even runs, is that
        # cancel() was called: Task.cancelling() (3.11+) counts pending
        # cancellation requests, so >0 means "already asked to stop".
        seen_state_at_call_time["cancel_requested"] = slow.cancelling() > 0
        return [_hit(1), _hit(2)]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    await chat_router._retrieve_context("प्रश्न", session.profile, session)

    assert seen_state_at_call_time.get("cancel_requested") is True


@pytest.mark.asyncio
async def test_a_miss_cancels_a_still_running_prepare_even_with_the_wait_off(monkeypatch):
    # With the wait off (0): no waiting, but a prepare that is STILL running
    # when the miss is decided must be cancelled, not left to keep contending
    # with this turn's own request to Ollama. This is unconditional on the
    # wait -- it is what actually removes the contention, not the wait's
    # presence or absence.
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "rag_early_prime_wait_seconds", 0.0)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1), _hit(2)]

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await _session()
    slow = asyncio.create_task(_delayed_prepare(session, 5.0, [9, 9]))  # a different draft
    session.preparing = slow

    rc = await chat_router._retrieve_context("प्रश्न", session.profile, session)
    assert rc.primed is None

    for _ in range(10):
        if slow.cancelled() or slow.done():
            break
        await asyncio.sleep(0)
    assert slow.cancelled()


@pytest.mark.asyncio
async def test_chat_prepare_endpoint_tracks_and_clears_the_in_flight_task(monkeypatch):
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1)]

    async def fake_prime(messages, model=None):
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_router.client, "prime", fake_prime)
    session = await _session()

    async def fake_get_or_create(session_id, profile):
        return session

    monkeypatch.setattr(chat_router.store, "get_or_create", fake_get_or_create)

    from app.schemas import PrepareRequest
    result = await chat_router.chat_prepare(
        PrepareRequest(message="प्रश्न", session_id="whatever", profile=None))
    assert result == {"accepted": True}
    assert session.preparing is not None
    task = session.preparing
    # Two things to wait for, not one: the task finishing, THEN its
    # done-callbacks actually running -- add_done_callback schedules them via
    # call_soon, so `task.done()` can be True for a tick or two before the
    # callback that clears session.preparing has actually executed.
    for _ in range(20):
        await asyncio.sleep(0)
        if task.done():
            break
    assert task.done()
    for _ in range(20):
        if session.preparing is None:
            break
        await asyncio.sleep(0)
    assert session.preparing is None, "the done-callback must clear itself once finished"


@pytest.mark.asyncio
async def test_a_prepare_finishing_during_the_grace_wait_does_not_crash_the_turn(monkeypatch):
    # Live regression, 2026-09-14: `session.preparing` is cleared to None by
    # the task's OWN done-callback (see chat_prepare's _clear_if_still_current)
    # the instant the loop gets a tick to run it -- which is exactly what
    # happens while `_retrieve_context` is awaiting that same task for the
    # grace period below. The code used to keep re-reading `session.preparing`
    # after that await and crashed with AttributeError ('NoneType' object has
    # no attribute 'done') on a real live run. Dispatched through the actual
    # chat_prepare endpoint, not a bare asyncio.create_task, so the real
    # done-callback wiring is what races here, same as production.
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(settings, "rag_early_prime_wait_seconds", 0.35)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1), _hit(2)]

    async def fake_prime(messages, model=None):
        await asyncio.sleep(0.02)  # finishes comfortably within the 0.35s grace
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_router.client, "prime", fake_prime)
    session = await _session()

    async def fake_get_or_create(session_id, profile):
        return session

    monkeypatch.setattr(chat_router.store, "get_or_create", fake_get_or_create)

    from app.schemas import PrepareRequest
    await chat_router.chat_prepare(
        PrepareRequest(message="प्रश्न", session_id="whatever", profile=None))
    assert session.preparing is not None

    rc = await chat_router._retrieve_context("प्रश्न", session.profile, session)
    assert rc is not None  # must not raise


@pytest.mark.asyncio
async def test_dispatching_a_prepare_cancels_a_still_running_reprime(monkeypatch):
    # Root-caused 2026-09-14 chasing why prepares almost never landed a catch
    # live: ollama_reprime_after_reply fires after EVERY reply and measured
    # 6-8s on a grown conversation, and Ollama serialises gemma2 access on
    # this box -- so a prepare dispatched a moment after the reply (the
    # normal case) queued its own prime() call behind re-prime's, burning
    # most or all of the student's think-time before the guess had even
    # started. A newly dispatched prepare must cancel a still-running
    # re-prime instead of queuing behind it.
    monkeypatch.setattr(settings, "rag_early_prime_enabled", True)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def fake_retrieve(*a, **k):
        return [_hit(1)]

    async def fake_prime(messages, model=None):
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_router.client, "prime", fake_prime)
    session = await _session()

    async def slow_reprime(messages, model=None):
        await asyncio.sleep(5.0)
        return {"prompt_eval_duration": 0, "prompt_eval_count": 0}

    monkeypatch.setattr(chat_router.client, "prime", slow_reprime)
    chat_router._reprime_after_reply(session, None, None)
    still_running = session.repriming
    assert still_running is not None
    monkeypatch.setattr(chat_router.client, "prime", fake_prime)  # prepare's own call

    async def fake_get_or_create(session_id, profile):
        return session

    monkeypatch.setattr(chat_router.store, "get_or_create", fake_get_or_create)

    from app.schemas import PrepareRequest
    await chat_router.chat_prepare(
        PrepareRequest(message="प्रश्न", session_id="whatever", profile=None))

    for _ in range(10):
        if still_running.cancelled() or still_running.done():
            break
        await asyncio.sleep(0)
    assert still_running.cancelled()
