"""The per-turn trace, and the one metric that is computed rather than observed.

These guard a specific way of being useless: a metrics panel that renders zeros
looks like a fast turn with a healthy gate, and is indistinguishable from one
that was never filled in. Every test here is about the trace surviving a path,
not about the numbers being pretty.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import RetrievalMetrics, TurnMetrics  # noqa: E402
from app.services.rag import retrieval  # noqa: E402
from app.services.rag.metrics import format_turn, groundedness  # noqa: E402
from app.services.rag.retrieval import fit_to_budget  # noqa: E402
from app.services.rag.store import LibraryStore, Retrieved  # noqa: E402

DIMS = 8


def _axis(i: int, dims: int = DIMS):
    v = [0.0] * dims
    v[i % dims] = 1.0
    return v


class _Chunk:
    def __init__(self, ordinal, text, heading=""):
        self.ordinal, self.text, self.heading = ordinal, text, heading
        self.page_start = self.page_end = 1


TEXTS = [
    "A tissue is a group of cells similar in structure that work together.",
    "Xylem is a complex tissue that carries water up through the stem.",
    "The capital of India is New Delhi, a city in the north.",
]


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(str(tmp_path / "l.db"), DIMS, "bge-m3")
    s.open()
    doc = s.add_document(
        filename="sci.pdf", title="Science", grade=9, subject="Science",
        sha256="h", pages=1, created_at="2026-01-01T00:00:00+00:00", language="en",
    )
    s.add_chunks(
        doc, 9, "Science",
        [(_Chunk(i, t), _axis(i)) for i, t in enumerate(TEXTS)],
        "en",
    )
    yield s
    s.close()


def _hit(cid, text, distance=0.3):
    return Retrieved(
        chunk_id=cid, text=text, heading="", page_start=1, page_end=1,
        distance=distance, document_title="Science", grade=9, subject="Science",
        language="en",
    )


# -- the trace survives every path ----------------------------------------

@pytest.mark.asyncio
async def test_a_successful_turn_fills_the_whole_funnel(store, monkeypatch):
    async def _near(_text, model=None):
        return _axis(0)

    monkeypatch.setattr(retrieval, "embed_query", _near)
    trace = RetrievalMetrics()
    # The session language, as the chat router passes it. Without one the
    # sniffer is unsure and deliberately takes the loosest ceiling, so the
    # language recorded would be the fallback rather than the student's.
    hits = await retrieval.retrieve(
        store, "what is a tissue", grade=9, language="English", metrics=trace
    )

    assert hits
    assert trace.query_language == "en"
    assert trace.dense_hits >= 1
    assert trace.gate_survivors >= 1
    assert trace.returned == len(hits)
    assert trace.abstained is False
    assert trace.abstain_reason == ""
    assert trace.best_distance is not None
    # The gate cleared, so there was room to spare. Reported rather than
    # derived in the UI because the ceiling that produced it is per language.
    assert trace.headroom is not None and trace.headroom > 0
    # The clock ran. Zero here is the failure mode this file exists for: it
    # renders as a fast turn instead of as an unmeasured one.
    assert trace.total_ms > 0


@pytest.mark.asyncio
async def test_the_trace_explains_an_abstention_rather_than_going_blank(
    store, monkeypatch
):
    """"No sources" is the same string for four different bugs.

    An empty library, a gate doing its job, a gate tuned wrong and a crashed
    embedding call all reach the student as an uncited answer. The distances
    that separate them exist only inside retrieve(), so they have to leave with
    the trace or they are gone.
    """
    async def _far(_text, model=None):
        return _axis(7)              # an axis no chunk occupies

    monkeypatch.setattr(retrieval, "embed_query", _far)
    trace = RetrievalMetrics()
    hits = await retrieval.retrieve(
        store, "who won the 1998 world cup", grade=9, metrics=trace
    )

    assert hits == []
    assert trace.abstained is True
    assert trace.gate_survivors == 0
    # It got far enough to measure a distance, so the gate declined -- it did
    # not fail to search.
    assert trace.dense_hits > 0
    assert trace.best_distance is not None
    assert trace.headroom is not None and trace.headroom < 0
    assert "ceiling" in trace.abstain_reason


@pytest.mark.asyncio
async def test_a_failed_embedding_is_traced_as_a_failure_not_an_abstention(
    store, monkeypatch
):
    """The case that must never read as 'the library does not cover this'.

    retrieve() swallows the exception on purpose -- an unaided answer beats a
    500 -- which is exactly why the trace has to carry the reason out. Both
    paths return [], and only the reason tells them apart.
    """
    async def _boom(_text, model=None):
        raise RuntimeError("ollama is down")

    monkeypatch.setattr(retrieval, "embed_query", _boom)
    trace = RetrievalMetrics()
    hits = await retrieval.retrieve(store, "what is a tissue", grade=9, metrics=trace)

    assert hits == []
    assert "retrieval failed" in trace.abstain_reason
    assert "ollama is down" in trace.abstain_reason
    # Timed even though it threw: the student still waited for the round trip.
    assert trace.total_ms > 0


@pytest.mark.asyncio
async def test_retrieve_still_works_without_a_trace(store, monkeypatch):
    """The metrics argument is optional; the library router passes nothing."""
    async def _near(_text, model=None):
        return _axis(0)

    monkeypatch.setattr(retrieval, "embed_query", _near)
    assert await retrieval.retrieve(store, "what is a tissue", grade=9)


# -- the budget ------------------------------------------------------------

def test_the_budget_records_what_it_dropped():
    """`context_tokens` is what prefill will actually re-read on CPU.

    Held against prefill_ms it is the only pair that shows RAG's real latency
    cost; on its own, a passage count says nothing, because a Devanagari
    passage is three times an English one at the same character length.
    """
    long_hits = [_hit(i, "ऊतक कोशिकाओं का समूह है। " * 40) for i in range(4)]
    trace = RetrievalMetrics()
    kept = fit_to_budget(long_hits, token_budget=1200, metrics=trace)

    assert 0 < len(kept) < 4
    assert trace.returned == len(kept)
    assert trace.dropped_over_budget == 4 - len(kept)
    assert trace.context_budget == 1200
    assert trace.context_tokens > 0


# -- groundedness ----------------------------------------------------------

def test_an_answer_taken_from_the_passage_scores_high():
    hits = [_hit(1, TEXTS[0])]
    score, note = groundedness(
        "A tissue is a group of cells that are similar in structure and work "
        "together.",
        hits,
    )
    assert note == ""
    assert score is not None and score > 0.8


def test_an_answer_that_ignored_the_passage_scores_low():
    """The failure the citation list makes dangerous.

    The excerpt is about tissues, the reply is about the solar system, and the
    student still sees "From your textbook - p. 63" underneath it.
    """
    hits = [_hit(1, TEXTS[0])]
    score, _ = groundedness(
        "Jupiter is the largest planet, and its enormous gravity shepherds the "
        "asteroid belt.",
        hits,
    )
    assert score is not None and score < 0.4


def test_devanagari_inflection_does_not_read_as_ungrounded():
    """Why trigrams, and not whole words.

    कोशिका in the book and कोशिकाओं in the answer are the same word inflected,
    and share no token at all. Matching whole words would score a perfectly
    grounded Hindi answer near zero -- silently, and only for the students the
    multilingual work exists for. This is the same reasoning that put
    `tokenize='trigram'` on the FTS5 index.
    """
    hits = [_hit(1, "ऊतक कोशिका का समूह है जो मिलकर कार्य करता है।")]
    score, _ = groundedness("ऊतक कोशिकाओं का समूह है जो कार्य करती हैं।", hits)
    assert score is not None and score > 0.7


def test_an_unaided_answer_is_not_scored():
    """None, not 0.0. An answer with no passages is not an ungrounded answer,
    and scoring it zero would drag the average down for the case the gate got
    right."""
    score, note = groundedness("Photosynthesis is how plants make food.", [])
    assert score is None
    assert "without the library" in note


def test_a_translated_answer_is_not_scored_as_ungrounded():
    """The case that made this metric lie, seen live on the Class 6 corpus.

    A Hindi answer written from an English page shares no wording with its
    source by construction -- that is the cross-lingual retrieval bge-m3 was
    chosen for. Scored, it reads 0.00, which is indistinguishable from the
    model having ignored the passages entirely. Any measurement that would work
    here costs a model call, so declining to score is the honest option and the
    note is how the panel says so.
    """
    hits = [_hit(1, TEXTS[0])]
    score, note = groundedness(
        "ऊतक कोशिकाओं का एक समूह है जो मिलकर कार्य करता है।", hits
    )
    assert score is None
    assert "devanagari" in note and "latin" in note


# -- the log line ----------------------------------------------------------

def test_the_log_line_survives_a_turn_with_nothing_measured():
    """It is emitted on every turn, including the ones where retrieval
    abstained and every optional number is None."""
    line = format_turn(TurnMetrics())
    assert "turn" in line and "ttft" in line


def test_the_log_line_only_mentions_a_retry_when_one_happened():
    """A socratic re-ask is a second full generation and the largest latency
    outlier this app has. A zero on every line would hide it in the noise."""
    assert "socratic retry" not in format_turn(TurnMetrics())
    assert "socratic retry" in format_turn(TurnMetrics(retry_ms=980.0))


def test_a_one_token_reply_is_not_perfectly_grounded():
    """The page-load warm-up generates exactly one token.

    A two-word reply has a handful of trigrams, all of them common, so it
    matches any passage at all and scored a clean 1.00 -- which then sat in the
    log looking like the best-grounded turn of the session.
    """
    hits = [_hit(1, TEXTS[0])]
    score, note = groundedness("A", hits)
    assert score is None
    assert "too short" in note


def test_the_log_line_omits_a_rate_it_cannot_compute():
    """Ollama divides tokens by a nanosecond duration, so a one-token
    generation reports ~1000000 tok/s. Printing it invites averaging it."""
    one_token = TurnMetrics(completion_tokens=1, tokens_per_second=1000000.0)
    assert "tok/s" not in format_turn(one_token)
    real = TurnMetrics(completion_tokens=48, tokens_per_second=13.4)
    assert "13.4 tok/s" in format_turn(real)


def test_a_warm_up_is_labelled_so_it_is_not_read_as_a_turn():
    assert format_turn(TurnMetrics(), "warm-up").startswith("warm-up ")
    assert format_turn(TurnMetrics()).startswith("turn ")


# -- the off switch --------------------------------------------------------

@pytest.mark.asyncio
async def test_metrics_off_means_no_trace_is_filled(store, monkeypatch):
    """METRICS_ENABLED=false has to reach retrieval, not just the response.

    Gating only the payload would leave every stage still timing itself and
    still computing groundedness, which is the cost the switch exists to
    remove -- and would read as "off" while doing all the work.
    """
    from app.routers import chat as chat_router

    async def _near(_text, model=None):
        return _axis(0)

    monkeypatch.setattr(retrieval, "embed_query", _near)
    monkeypatch.setattr(chat_router.settings, "metrics_enabled", False)
    monkeypatch.setattr(chat_router.library, "store", store)

    context, sources, hits, trace = await chat_router._retrieve_context(
        "what is a tissue", None
    )
    assert hits, "retrieval itself must be unaffected by the switch"
    assert sources, "citations are not metrics -- they stay"
    assert trace is None


@pytest.mark.asyncio
async def test_metrics_on_still_fills_the_trace(store, monkeypatch):
    from app.routers import chat as chat_router

    async def _near(_text, model=None):
        return _axis(0)

    monkeypatch.setattr(retrieval, "embed_query", _near)
    monkeypatch.setattr(chat_router.settings, "metrics_enabled", True)
    monkeypatch.setattr(chat_router.library, "store", store)

    _, _, hits, trace = await chat_router._retrieve_context("what is a tissue", None)
    assert hits
    assert trace is not None and trace.returned == len(hits)
