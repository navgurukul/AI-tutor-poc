"""Hybrid retrieval (rag.hybrid), ported from AFE-Learning-App's rag-engine/src:
fusion, merging, the token budget, the context block and section resolution."""

from app.services.rag import hybrid as engine
from app.services.rag.fusion import reciprocal_rank_fusion
from app.services.rag.merge import merge_adjacent_chunks
from app.services.rag.sections import resolve_section
from app.services.rag.models import Chunk, SectionInfo


def chunk(id, seq, text, doc="d", score=0.0, **meta):
    return Chunk(id=id, doc_id=doc, seq=seq, text=text, metadata=meta, score=score)


# -- fusion ------------------------------------------------------------------
def test_rrf_sums_reciprocal_ranks_and_records_sources():
    fused = reciprocal_rank_fusion([[(1, "dense"), (2, "dense")], [(2, "lexical"), (3, "lexical")]])
    assert [f["id"] for f in fused] == [2, 1, 3]
    top = fused[0]
    assert top["matched_via"] == ["dense", "lexical"]
    assert abs(top["score"] - (1 / 62 + 1 / 61)) < 1e-12


def test_rrf_ties_keep_first_seen_order():
    fused = reciprocal_rank_fusion([[(7, "dense")], [(8, "lexical")]])
    assert [f["id"] for f in fused] == [7, 8]


# -- merge -------------------------------------------------------------------
def test_adjacent_chunks_merge_and_the_overlap_is_stripped():
    a = chunk(1, 0, "one two three four five six seven", score=0.5)
    b = chunk(2, 1, "four five six seven eight nine", score=0.2)
    merged = merge_adjacent_chunks([b, a])
    assert len(merged) == 1
    assert merged[0].text == "one two three four five six seven eight nine"
    assert merged[0].score == 0.5


def test_non_adjacent_chunks_stay_apart_and_sort_by_score():
    merged = merge_adjacent_chunks([chunk(1, 0, "a", score=0.1), chunk(2, 5, "b", score=0.9)])
    assert [c.id for c in merged] == [2, 1]


def test_chunks_of_different_documents_never_merge():
    merged = merge_adjacent_chunks([chunk(1, 0, "a", doc="x"), chunk(2, 1, "b", doc="y")])
    assert len(merged) == 2


# -- budget ------------------------------------------------------------------
def test_token_estimate_is_words_over_three_quarters_rounded_up():
    assert engine.approx_tokens("a b c") == 4
    assert engine.approx_tokens("one two three four") == 6


def test_budget_always_keeps_the_first_chunk_then_stops_before_overflow():
    words = " ".join(["w"] * 300)  # 400 tokens each
    kept = engine.apply_token_budget([chunk(i, i * 3, words) for i in range(3)], 800)
    assert len(kept) == 2


def test_oversized_chunk_is_cut_with_an_ellipsis_before_budgeting():
    text = " ".join("w{}".format(i) for i in range(1000))
    kept = engine.apply_token_budget([chunk(1, 0, text)], 800, max_chunk_tokens=450)
    assert kept[0].text.endswith("…")
    assert len(kept[0].text.split()) == 337  # int(450 * 0.75) words


# -- context block -----------------------------------------------------------
def test_context_block_matches_afe_format():
    c1 = chunk(1, 0, "Inertia is...", title="iesc109.pdf", chapterTitle="Force", topicTitle="First law")
    c2 = chunk(2, 0, "Plain.", title="hesc101.pdf")
    assert engine.build_context_block([c1, c2]) == (
        "[1] iesc109 - Force > First law\nInertia is...\n\n[2] hesc101\nPlain."
    )


# -- sections ----------------------------------------------------------------
SECTIONS = [
    SectionInfo("d", "chapter", 3, "Chapter 3 Atoms"),
    SectionInfo("d", "topic", 31, "3.1 Dalton"),
    SectionInfo("d", "topic", 21, "Photosynthesis in plants"),
]


def test_explicit_chapter_number_resolves():
    assert resolve_section("what is in chapter 3", SECTIONS).id == 3


def test_dotted_number_resolves_to_a_topic():
    assert resolve_section("explain 3.1", SECTIONS).id == 31


def test_title_words_must_cover_60_percent_to_match():
    assert resolve_section("tell me about photosynthesis in plants", SECTIONS).id == 21
    assert resolve_section("what is inertia", SECTIONS) is None
