"""The lexical leg, fusion, the gate and the token budget.

Every test here guards something that fails silently. The MATCH-builder tests
in particular exist because the original check passed -- it tested a bare
keyword, which is the one shape that always worked.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.gate import (  # noqa: E402
    gate_dense_hits,
    resolve_query_language,
    sniff_language,
)
from app.services.rag.query import build_match_query, estimate_tokens  # noqa: E402
from app.services.rag.retrieval import _rrf, fit_to_budget  # noqa: E402
from app.services.rag.store import LibraryStore, Retrieved  # noqa: E402

DIMS = 8


def _axis(i: int, dims: int = DIMS):
    """A unit vector along one axis, so cosine can actually tell chunks apart."""
    v = [0.0] * dims
    v[i % dims] = 1.0
    return v


class _Chunk:
    def __init__(self, ordinal, text, heading=""):
        self.ordinal, self.text, self.heading = ordinal, text, heading
        self.page_start = self.page_end = 1


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(str(tmp_path / "l.db"), DIMS, "bge-m3")
    s.open()
    doc = s.add_document(
        filename="sci.pdf", title="Science", grade=9, subject="Science",
        sha256="h", pages=1, created_at="2026-01-01T00:00:00+00:00", language="en",
    )
    texts = [
        "A tissue is a group of cells similar in structure that work together.",
        "Xylem is a complex tissue that carries water up through the stem.",
        "The capital of India is New Delhi, a city in the north.",
    ]
    # Distinct *directions*, not distinct magnitudes. The store uses cosine, so
    # [0.1]*8 and [0.3]*8 are the same vector as far as it is concerned -- a
    # fixture built that way makes every chunk equidistant and every gate test
    # vacuous.
    s.add_chunks(
        doc, 9, "Science",
        [(_Chunk(i, t), _axis(i)) for i, t in enumerate(texts)],
        "en",
    )
    yield s
    s.close()


def _hit(cid, distance):
    return Retrieved(
        chunk_id=cid, text="t{}".format(cid), heading="", page_start=1, page_end=1,
        distance=distance, document_title="Science", grade=9, subject="Science",
        language="en",
    )


# -- the MATCH string ------------------------------------------------------

@pytest.mark.parametrize("question", [
    "What is a tissue",
    "Explain tissue",
    "define tissue please",
    "What is a tissue?",
    "Can you tell me what a tissue is?",
])
def test_a_natural_language_question_returns_rows(store, question):
    """The test the plan insists on.

    Passed straight to FTS5 every one of these returns [] -- the implicit AND
    requires every word in the passage, and under trigram a sub-3-character
    term produces no tokens and zeroes the conjunction. Without this test the
    builder regresses the first time someone simplifies it.
    """
    match = build_match_query(question)
    assert match, "the builder produced nothing"
    hits = store.search_lexical(match, grade=9, k=50)
    assert len(hits) > 0, "{!r} -> {!r} matched nothing".format(question, match)


def test_the_raw_question_is_what_fails(store):
    """Demonstrates the defect the builder exists to fix."""
    assert store.search_lexical("What is a tissue", grade=9, k=50) == []
    assert store.search_lexical("Explain tissue", grade=9, k=50) == []
    # The one shape that always worked, and the reason the original check passed.
    assert len(store.search_lexical("tissue", grade=9, k=50)) > 0


def test_terms_are_or_ed_never_and_ed():
    match = build_match_query("What is a plant tissue")
    assert " OR " in match
    assert " AND " not in match


def test_short_terms_and_stopwords_are_dropped():
    match = build_match_query("What is a cell")
    assert '"is"' not in match and '"a"' not in match
    assert '"cell"' in match


def test_embedded_quotes_are_doubled():
    match = build_match_query('what is a "tissue" exactly')
    assert '""tissue""' in match


def test_devanagari_survives_the_builder(store):
    match = build_match_query("ऊतक क्या है?")
    assert '"ऊतक"' in match


def test_bm25_still_finds_an_exact_devanagari_term(tmp_path):
    s = LibraryStore(str(tmp_path / "hi.db"), DIMS, "bge-m3")
    s.open()
    doc = s.add_document(
        filename="hi.pdf", title="विज्ञान", grade=9, subject="Science",
        sha256="h2", pages=1, created_at="2026-01-01T00:00:00+00:00", language="hi",
    )
    s.add_chunks(
        doc, 9, "Science",
        [(_Chunk(0, "ऊतक कोशिकाओं का समूह है जो कार्य करता है।"), [0.1] * DIMS)],
        "hi",
    )
    assert len(s.search_lexical('"कार्य"', grade=9, k=10)) == 1
    s.close()


# -- fusion ----------------------------------------------------------------

def test_rrf_rewards_agreement_between_the_legs():
    dense = [_hit(1, 0.2), _hit(2, 0.3), _hit(3, 0.4)]
    lexical = [_hit(3, 1.0), _hit(1, 1.0)]
    fused = _rrf([dense, lexical], k=60)
    # 3 is second-best on dense but top on lexical; 1 is top on dense and
    # second on lexical. Both beat 2, which only one leg found.
    assert fused[-1].chunk_id == 2


def test_rrf_keeps_the_copy_with_a_real_distance():
    dense = [_hit(1, 0.21)]
    lexical = [_hit(1, 1.0)]
    assert _rrf([dense, lexical])[0].distance == 0.21


# -- the gate --------------------------------------------------------------

def test_the_ceiling_lets_the_tutor_decline():
    """Nothing close enough -> no context at all, in any language."""
    far = [_hit(1, 0.80), _hit(2, 0.85)]
    for language in ("en", "hi", "mr", "romanized"):
        survivors, _ = gate_dense_hits(far, language)
        assert survivors == [], language


def test_the_relative_gate_normalises_the_language_offset():
    """A correct Hindi hit must survive at a distance that fails on English.

    Measured on the Class 6 corpus, correct chunks sit at 0.313-0.536 for a
    Hindi question and 0.286-0.439 for an English one, so the ceilings are
    0.58 and 0.51. A hit at 0.536 is the Hindi student's right answer and an
    English student's noise -- which is the whole reason one global threshold
    cannot serve both, and why it failed silently for exactly the students the
    feature exists for.
    """
    hindi_shaped = [_hit(1, 0.536), _hit(2, 0.56), _hit(3, 0.82)]
    survivors, _ = gate_dense_hits(hindi_shaped, "hi")
    assert [h.chunk_id for h in survivors] == [1, 2]
    # The same distances, judged as English, do not clear the ceiling at all.
    assert gate_dense_hits(hindi_shaped, "en")[0] == []


def test_the_margin_drops_the_off_topic_tail():
    hits = [_hit(1, 0.21), _hit(2, 0.28), _hit(3, 0.77)]
    survivors, _ = gate_dense_hits(hits, "en")
    assert [h.chunk_id for h in survivors] == [1, 2]


# -- query language --------------------------------------------------------

def test_the_session_wins_over_the_text():
    assert resolve_query_language("Hindi", "what is a tissue") == "hi"
    assert resolve_query_language("Marathi", "ऊतक क्या है") == "mr"


def test_romanized_indic_is_its_own_bucket():
    """Read as English it takes the strictest ceiling and loses the answer."""
    code, confident = sniff_language("utak kya hai")
    assert (code, confident) == ("romanized", True)
    assert resolve_query_language(None, "utak kya hai") == "romanized"


def test_an_english_session_typing_romanized_indic_is_overridden():
    """The toggle says English because the student never changed it."""
    assert resolve_query_language("English", "utak kya hai") == "romanized"
    assert resolve_query_language("English", "what is a tissue") == "en"


def test_an_unsure_fallback_takes_the_loosest_ceiling():
    """A false accept costs one noisy passage; a false reject costs the answer."""
    # Devanagari cannot be split into Hindi vs Marathi by script alone.
    code, confident = sniff_language("ऊतक क्या है")
    assert not confident
    assert resolve_query_language(None, "ऊतक क्या है") in ("hi", "mr", "romanized")


# -- the token budget ------------------------------------------------------

def test_devanagari_costs_more_tokens_per_character():
    english = "Water moves through the xylem. " * 60
    hindi = "ऊतक कोशिकाओं का समूह है। " * 60
    assert abs(len(english) - len(hindi)) < len(english) * 0.35
    assert estimate_tokens(hindi) > estimate_tokens(english) * 2


def test_k_falls_before_a_passage_is_cut():
    """Three whole passages beat four half ones."""
    long_hit = lambda cid: Retrieved(  # noqa: E731
        chunk_id=cid, text="ऊतक कोशिकाओं का समूह है। " * 40, heading="",
        page_start=1, page_end=1, distance=0.3, document_title="विज्ञान",
        grade=9, subject="Science", language="hi",
    )
    hits = [long_hit(i) for i in range(4)]
    kept = fit_to_budget(hits, token_budget=1200)
    assert 0 < len(kept) < 4
    # Nothing was truncated -- every kept passage is whole.
    assert all(k.text == hits[0].text for k in kept)


def test_the_first_passage_always_survives():
    huge = Retrieved(
        chunk_id=1, text="x" * 20000, heading="", page_start=1, page_end=1,
        distance=0.2, document_title="Science", grade=9, subject="Science",
        language="en",
    )
    assert len(fit_to_budget([huge], token_budget=10)) == 1


# -- abstention ------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_empty_dense_leg_never_consults_bm25(store, monkeypatch):
    """Closed-01: the dense leg decides *whether* there is an answer.

    Without this, a question the library does not cover empties the dense leg,
    RRF still has fifty lexical candidates to rank, and the top four reach the
    prompt with a chapter and page attached. BM25 alone can never put a
    citation in front of a student.
    """
    from app.services.rag import retrieval

    async def _far_vector(_text, model=None):
        # An axis no chunk occupies: cosine distance 1.0 to all of them, which
        # is past every ceiling. (A uniform vector would NOT work -- it is
        # parallel to nothing in particular but equidistant from everything.)
        return _axis(7)

    consulted = []
    original = store.search_lexical

    def _spy(*args, **kwargs):
        consulted.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(retrieval, "embed_query", _far_vector)
    monkeypatch.setattr(store, "search_lexical", _spy)

    caplog_seen = []
    original_warn = retrieval.logger.warning
    retrieval.logger.warning = lambda *a, **k: caplog_seen.append(a)
    try:
        hits = await retrieval.retrieve(store, "who won the 1998 world cup", grade=9)
    finally:
        retrieval.logger.warning = original_warn

    assert hits == []
    assert consulted == [], "BM25 was consulted after the gate emptied"
    # [] because the gate emptied, not because retrieve() swallowed an error.
    assert not caplog_seen, "retrieve() failed rather than gated: {}".format(caplog_seen)


@pytest.mark.asyncio
async def test_a_covered_question_does_consult_bm25(store, monkeypatch):
    from app.services.rag import retrieval

    async def _near_vector(_text, model=None):
        return _axis(0)              # sits exactly on the first chunk

    consulted = []
    original = store.search_lexical

    def _spy(*args, **kwargs):
        consulted.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(retrieval, "embed_query", _near_vector)
    monkeypatch.setattr(store, "search_lexical", _spy)

    hits = await retrieval.retrieve(store, "what is a tissue", grade=9)
    assert hits, "a covered question should retrieve"
    assert consulted, "BM25 should run once the gate passes"


@pytest.mark.asyncio
async def test_lexical_hits_must_clear_the_gate_or_neighbour_one(store, monkeypatch):
    """An unrelated lexical hit must not ride in on a good one."""
    from app.services.rag import retrieval

    async def _near_first(_text, model=None):
        return _axis(0)

    monkeypatch.setattr(retrieval, "embed_query", _near_first)
    # "capital of India" is chunk 3 -- lexically matchable, semantically far.
    hits = await retrieval.retrieve(store, "what is the capital city", grade=9, k=10)
    texts = " ".join(h.text for h in hits)
    assert "New Delhi" not in texts or all(
        h.distance < 1.0 for h in hits
    ), "an off-topic lexical hit reached the prompt"


def test_a_zero_ceiling_disables_retrieval_for_that_bucket(monkeypatch):
    """Romanized Indic, where bge-m3 ranks noise above the correct chunk.

    Not a tight threshold -- a measured absence of signal. Nothing can clear a
    ceiling of 0.0, so the tutor answers unaided rather than citing a page
    about galaxies.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "rag_ceiling_romanized", 0.0)
    close = [_hit(1, 0.05), _hit(2, 0.06)]
    survivors, ceiling = gate_dense_hits(close, "romanized")
    assert survivors == []
    assert ceiling == 0.0
    # ...and the other buckets are unaffected.
    assert gate_dense_hits(close, "en")[0]
