"""select_evidence: embedding-similarity sentence selection, NOT lexical
keyword overlap.

The whole reason this exists as a separate mechanism from trim_passage's
head-taking is a real incident: scoring by shared words with the question
broke an answer on 2026-09-09 (kept "there are three types", dropped what
they were, because the topic sentence repeats the question's own vocabulary
and the sentence carrying the actual fact does not). These tests pin that
this version is judged by a caller-supplied embedding signal instead, so a
fact-bearing sentence with LOW lexical overlap but HIGH semantic similarity
still wins over a topic sentence with high lexical overlap -- the specific
property the 2026-09-09 mechanism got backwards.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag import retrieval as retrieval_module  # noqa: E402
from app.services.rag.retrieval import (  # noqa: E402
    select_evidence,
    select_evidence_for_hits,
)
from app.services.rag.store import Retrieved  # noqa: E402


def _hit(chunk_id, text):
    return Retrieved(
        chunk_id=chunk_id, text=text, heading="h", page_start=1, page_end=1,
        distance=0.3, document_title="t", grade=6, subject="Geography",
    )


# Four short sentences (danda-terminated, so _SENTENCE_SPLIT actually splits
# them): a preamble, a topic sentence sharing the question's own words, the
# fact-bearing sentence using DIFFERENT words, and a trailing detail.
PASSAGE = (
    "भारत में कई प्रकार की मिट्टियाँ पाई जाती हैं। "
    "काली मिट्टी को रेगुर मिट्टी भी कहा जाता है। "
    "यह मुख्य रूप से दक्कन के पठार में पाई जाती है। "
    "यह कपास की खेती के लिए उपयुक्त होती है।"
)
QUESTION = "काली मिट्टी कहाँ पाई जाती है"


def _sentences(text):
    return [s.strip() for s in retrieval_module._SENTENCE_SPLIT.split(text) if s.strip()]


def _unit_at_cosine(c):
    """A 2-D unit vector whose cosine similarity to [1.0, 0.0] is exactly c.

    NOTE: a 1-D scalar vector will NOT do this -- cosine similarity is scale-
    invariant, so any two positive 1-D "vectors" always have cosine 1.0
    regardless of their values (this broke the first version of these tests).
    Needs a real angle, hence 2-D.
    """
    return [c, (1 - c * c) ** 0.5]


QUERY_VECTOR = [1.0, 0.0]


async def _fake_embed_matching_keywords(monkeypatch):
    """Rigs embed_documents so the sentence SHARING the question's words
    ("पाई जाती हैं", "मिट्टी") scores lower than the sentence that actually
    answers "where" (दक्कन के पठार) but shares fewer words -- the inverse of
    what lexical overlap would pick, proving this is judged on the embedding
    vectors alone, not word overlap.
    """
    sentences = _sentences(PASSAGE)
    fixed = {
        QUESTION: QUERY_VECTOR,
        sentences[0]: _unit_at_cosine(0.1),   # preamble -- irrelevant
        sentences[1]: _unit_at_cosine(0.3),   # topic sentence, shares "मिट्टी" -- still low here
        sentences[2]: _unit_at_cosine(0.95),  # the actual answer -- rigged HIGH despite fewer shared words
        sentences[3]: _unit_at_cosine(0.2),   # cotton-farming detail -- irrelevant to "where"
    }

    async def fake(texts, model=None):
        return [fixed[t] for t in texts]

    monkeypatch.setattr(retrieval_module, "embed_documents", fake)
    return sentences


@pytest.mark.asyncio
async def test_picks_the_semantically_relevant_sentence_not_the_lexical_one(monkeypatch):
    sentences = await _fake_embed_matching_keywords(monkeypatch)
    result = await select_evidence(PASSAGE, QUESTION, max_tokens=20)
    assert sentences[2] in result
    assert sentences[1] not in result, "must not fall back to the topic sentence just because it shares words"


@pytest.mark.asyncio
async def test_multiple_sentences_kept_in_original_passage_order(monkeypatch):
    sentences = _sentences(PASSAGE)
    fixed = {
        QUESTION: QUERY_VECTOR,
        sentences[0]: _unit_at_cosine(0.1),
        sentences[1]: _unit_at_cosine(0.9),
        sentences[2]: _unit_at_cosine(0.85),
        sentences[3]: _unit_at_cosine(0.1),
    }

    async def fake(texts, model=None):
        return [fixed[t] for t in texts]

    monkeypatch.setattr(retrieval_module, "embed_documents", fake)
    # 80: comfortably over both target sentences' combined estimated cost
    # (~65-70) without being so large it stops constraining anything.
    result = await select_evidence(PASSAGE, QUESTION, max_tokens=80)
    # Both high-scoring sentences fit the budget; they must come back in the
    # order they appear in the passage (1 then 2), not score order (also 1
    # then 2 here, but the ordering logic must not depend on that coincidence).
    assert result.index(sentences[1]) < result.index(sentences[2])


@pytest.mark.asyncio
async def test_respects_the_token_budget(monkeypatch):
    sentences = await _fake_embed_matching_keywords(monkeypatch)
    result = await select_evidence(PASSAGE, QUESTION, max_tokens=8)
    # Budget too small for the best sentence alone is still honoured by
    # keeping just that one best sentence (never truncated mid-sentence).
    assert result.strip() == sentences[2]


@pytest.mark.asyncio
async def test_falls_back_to_head_trim_on_embed_failure(monkeypatch):
    async def broken(texts, model=None):
        raise RuntimeError("ollama unreachable")

    monkeypatch.setattr(retrieval_module, "embed_documents", broken)
    result = await select_evidence(PASSAGE, QUESTION, max_tokens=20)
    sentences = _sentences(PASSAGE)
    assert result.strip() == sentences[0], "must fall back to trim_passage's head-taking, not raise"


@pytest.mark.asyncio
async def test_short_text_passes_through_unchanged(monkeypatch):
    async def should_not_be_called(texts, model=None):
        raise AssertionError("embed must not be called when already under the cap")

    monkeypatch.setattr(retrieval_module, "embed_documents", should_not_be_called)
    short = "यह एक छोटा वाक्य है।"
    assert await select_evidence(short, QUESTION, max_tokens=500) == short


@pytest.mark.asyncio
async def test_cap_zero_disables_extraction_entirely(monkeypatch):
    async def should_not_be_called(texts, model=None):
        raise AssertionError("embed must not be called when the cap is 0")

    monkeypatch.setattr(retrieval_module, "embed_documents", should_not_be_called)
    assert await select_evidence(PASSAGE, QUESTION, max_tokens=0) == PASSAGE


@pytest.mark.asyncio
async def test_select_evidence_for_hits_maps_over_every_hit(monkeypatch):
    sentences = await _fake_embed_matching_keywords(monkeypatch)
    hits = [_hit(1, PASSAGE), _hit(2, "छोटा।")]
    out = await select_evidence_for_hits(hits, QUESTION, max_tokens=20)
    assert len(out) == 2
    assert sentences[2] in out[0].text
    assert out[1].text == "छोटा।"  # already short, passed through
    assert out[0].chunk_id == 1 and out[1].chunk_id == 2  # identity preserved
