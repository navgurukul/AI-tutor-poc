"""A short follow-up keeps the previous passage instead of searching again.

Searched on its own words, "इसका एक उदाहरण दीजिए" ("give an example of this")
matched an unrelated passage and the answer was nonsense. The passage the
student is asking about is already in the conversation, so the right move is
to keep it -- and a turn that adds no passage is also the cheapest one.
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
from app.services.sessions import store  # noqa: E402


@pytest.mark.parametrize("message", [
    "इसका एक उदाहरण दीजिए।",
    "यह कैसे काम करता है?",
    "Explain this again",
    "Give me an example",
    "What does it mean?",
    "याचे उदाहरण द्या",
])
def test_referring_back_is_a_followup(message):
    assert chat_router._is_followup(message)


@pytest.mark.parametrize("message", [
    "What is photosynthesis?",
    "संज्ञा किसे कहते हैं?",
    "Can you explain how this data flow diagram connects the external entities to the data stores?",
    "",
])
def test_a_new_or_long_question_is_not(message):
    assert not chat_router._is_followup(message)


def _hit(cid):
    return Retrieved(chunk_id=cid, text="passage %d" % cid, heading="", page_start=1, page_end=1,
                     distance=0.3, document_title="t", grade=6, subject="s", language="Hindi")


class _Store:
    def __init__(self):
        self.asked = []

    def chunks_by_ids(self, ids):
        self.asked.append(list(ids))
        return [_hit(i) for i in ids]


@pytest.mark.asyncio
async def test_a_followup_reuses_the_last_passage_without_searching(monkeypatch):
    monkeypatch.setattr(settings, "rag_followup_reuse", True)
    fake = _Store()
    monkeypatch.setattr(chat_router.library, "store", fake)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)

    async def must_not_search(*a, **k):
        raise AssertionError("a follow-up must not search again")

    monkeypatch.setattr(chat_router, "retrieve", must_not_search)
    session = await store.create(TutorProfile(language="Hindi", level="Class 6"))
    session.last_hit_ids = [7, 9]

    rc = await chat_router._retrieve_context(
        "इसका एक उदाहरण दीजिए।", session.profile, session)
    assert rc.context == ""  # already in the conversation
    assert [h.chunk_id for h in rc.hits] == [7, 9]
    assert len(rc.sources) == 2
    assert fake.asked == [[7, 9]]


@pytest.mark.asyncio
async def test_no_previous_passage_means_a_normal_search(monkeypatch):
    monkeypatch.setattr(settings, "rag_followup_reuse", True)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)
    searched = []

    async def fake_retrieve(*a, **k):
        searched.append(True)
        return []

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await store.create(TutorProfile(language="Hindi", level="Class 6"))
    await chat_router._retrieve_context("इसका एक उदाहरण दीजिए।", session.profile, session)
    assert searched == [True]


@pytest.mark.asyncio
async def test_switched_off_means_a_normal_search(monkeypatch):
    monkeypatch.setattr(settings, "rag_followup_reuse", False)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)
    searched = []

    async def fake_retrieve(*a, **k):
        searched.append(True)
        return []

    monkeypatch.setattr(chat_router, "retrieve", fake_retrieve)
    session = await store.create(TutorProfile(language="Hindi", level="Class 6"))
    session.last_hit_ids = [7]
    await chat_router._retrieve_context("इसका एक उदाहरण दीजिए।", session.profile, session)
    assert searched == [True]


@pytest.mark.asyncio
async def test_a_followup_still_cancels_a_still_running_reprime(monkeypatch):
    # Live regression, 2026-09-16: the cancel-still-running-background-work
    # block used to sit AFTER both the pinned-corpus and follow-up early
    # returns, so a follow-up -- a very live path, "give an example of this"
    # reuses the previous passage with no new retrieval -- never reached it.
    # Caught live: a follow-up sent right after the previous reply let that
    # reply's re-prime keep running unchecked and stretch to 23.5s (normally
    # 5-8s) queuing behind the follow-up's own generation -- contention on
    # exactly the turn shape this mechanism exists to protect. The cancel now
    # runs before EITHER early-return path, not just the normal-search one.
    monkeypatch.setattr(settings, "rag_followup_reuse", True)
    monkeypatch.setattr(chat_router, "pinned_context", lambda *a, **k: None)
    fake = _Store()
    monkeypatch.setattr(chat_router.library, "store", fake)
    session = await store.create(TutorProfile(language="Hindi", level="Class 6"))
    session.last_hit_ids = [7, 9]

    async def never_finishes():
        await asyncio.sleep(5.0)

    still_running = asyncio.create_task(never_finishes())
    session.repriming = still_running

    await chat_router._retrieve_context("इसका एक उदाहरण दीजिए।", session.profile, session)

    for _ in range(10):
        if still_running.cancelled() or still_running.done():
            break
        await asyncio.sleep(0)
    assert still_running.cancelled()
