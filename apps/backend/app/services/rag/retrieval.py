"""Query-time retrieval: two legs, one gate, one fused list.

The shape, and why it is this shape:

The dense leg decides *whether* there is an answer. The lexical leg only
decides the order. That asymmetry is the whole design. A lexical match is
evidence of shared spelling, not of relevance -- BM25 will happily return fifty
passages for a question the library does not cover, and RRF will rank four of
them into the prompt with a chapter and page attached. An answer that is wrong
is a bad answer; an answer that is wrong and carries a citation to the
student's own textbook is a different category of failure.

So the gate sits on the dense leg *before* fusion. After RRF there are only
ranks -- the distances the gate needs are gone.
"""

import logging
import re
import time
from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Tuple

from app.config import settings
from app.schemas import RetrievalMetrics
from app.services.rag import spell
from app.services.rag.embeddings import embed_documents, embed_query
from app.services.rag.gate import gate_dense_hits, resolve_query_language
from app.services.rag.metrics import elapsed_ms
from app.services.rag.query import build_match_query, estimate_tokens
from app.services.rag.store import LibraryStore, Retrieved, StoreUnavailable

logger = logging.getLogger(__name__)


def _rrf(
    legs: Sequence[Sequence[Retrieved]], k: int = 60
) -> List[Retrieved]:
    """Reciprocal Rank Fusion.

    Rank-based on purpose: BM25 scores and cosine distances have no common
    scale, and any attempt to normalise one onto the other is a tuning
    parameter that drifts the moment either model changes. Ranks need nothing.

    k=60 is the standard damping constant; it flattens the difference between
    rank 1 and rank 2 enough that a passage found by both legs outranks one
    found brilliantly by either.
    """
    scores: Dict[int, float] = {}
    best: Dict[int, Retrieved] = {}
    for leg in legs:
        for rank, hit in enumerate(leg, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
            # Keep whichever copy carries a real distance -- the lexical leg
            # fills 1.0 as a placeholder and never a measured one.
            if hit.chunk_id not in best or hit.distance < best[hit.chunk_id].distance:
                best[hit.chunk_id] = hit
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [best[cid] for cid, _ in ordered]


def _abstain_reason(
    dense: Sequence[Retrieved], language: str, ceiling: float
) -> str:
    """Why nothing was retrieved, in a form that names the next thing to check.

    "no sources" is the same string for an empty library, a gate doing its job
    and a gate tuned wrong, and those need three different fixes.
    """
    if ceiling <= 0.0:
        return (
            "retrieval is off for {} -- no usable embedding signal, see "
            "rag_ceiling_romanized".format(language)
        )
    if not dense:
        return "the library holds no chunks for this grade"
    return "best hit {:.3f} is beyond the {} ceiling {:.2f}".format(
        dense[0].distance, language, ceiling
    )


# Markers of a workbook item rather than an explanation: fill-in blanks,
# imperative instructions, and the science books' activity boxes. 14-18% of the
# library's chunks carry several (measured 2026-09-11).
_EXERCISE_INSTRUCTIONS = re.compile(
    r"\.{6,}|_{4,}"
    r"|बनाइए|लिखिए|कीजिए|चुनिए|भरिए"
    r"|Activity \d|Let us (?:explore|investigate|experiment|record|identify)"
    r"|Fill in|Tick|Match the",
    re.IGNORECASE,
)
# Lettered and numbered sub-parts: (क) (ख), (a) (b), (i) ... (x).
#
# Counted ONLY alongside an instruction or a run of questions, because on their
# own they are how an NCERT chapter enumerates the thing it is explaining. The
# Class 10 Geography book teaches resource classification as
#     "(क) उत्पत्ति के आधार पर - जैव और अजैव (ख) समाप्यता के आधार पर ..."
# and when lettered parts counted by themselves, that list -- the literal answer
# to "संसाधनों के वर्गीकरण से आप क्या समझते हैं" -- was classed as an exercise and
# pushed behind a less relevant fragment (2026-09-14). An exercise is lettered
# parts PLUS something that asks the student to do or answer something.
_LETTERED_PARTS = re.compile(
    r"\((?:क|ख|ग|घ|ङ|a|b|c|d|e|i|ii|iii|iv|v|vi|vii|viii|ix|x)\)",
    re.IGNORECASE,
)
# Several questions in one chunk read as a question list. A single one does not:
# explanations open with rhetorical questions ("क्या आप भी ... समझते हैं?").
_MIN_QUESTIONS_FOR_A_LIST = 2


def looks_like_exercise(text: str) -> bool:
    """A chunk that asks questions rather than answers them, judged from text.

    The FALLBACK path. A library ingested by the structural pipeline carries
    `content_type` on every chunk, decided from the PDF's own geometry and
    typography, and `is_exercise` prefers that. This function is what remains
    for rows ingested before it, where the only evidence left is the words.

    Keeping it is not politeness to old data: re-ingesting a library takes
    hours on the target hardware, and a tutor that answered from multiple
    choice distractors in the meantime is the exact failure this guards.
    """
    instructions = len(_EXERCISE_INSTRUCTIONS.findall(text))
    questions = text.count("?")
    asks = instructions > 0 or questions >= _MIN_QUESTIONS_FOR_A_LIST
    if not asks:
        return False
    marks = (instructions
             + len(_LETTERED_PARTS.findall(text))
             + (1 if questions >= _MIN_QUESTIONS_FOR_A_LIST else 0))
    return marks >= 3 or (marks >= 2 and len(text.split()) < 60)


# Content types that ask a student to do something rather than explain
# anything. `caption` is deliberately NOT here -- a figure caption often
# carries the one sentence that names what the figure shows.
_EXERCISE_CONTENT_TYPES = frozenset({"exercise"})


def is_exercise(hit: Retrieved) -> bool:
    """Whether a retrieved passage is a workbook item rather than an explanation.

    Structural first, textual second. The classifier reads the page's
    geometry -- repeated option markers, a numbered question stem, an exercise
    heading -- which is evidence the text alone does not carry, and it reads it
    once at ingest rather than on every hit of every turn.

    It also settles a misclassification the text heuristic could not. Lettered
    parts "(क) ... (ख) ..." are how a chapter enumerates the thing it is
    explaining AND how it lists multiple-choice options; counting them from
    text alone classed the Class 10 Geography resource-classification list --
    the literal answer to "संसाधनों के वर्गीकरण से आप क्या समझते हैं" -- as an
    exercise (2026-09-14). Geometry separates the two; a regex cannot.
    """
    if hit.content_type:
        return hit.content_type in _EXERCISE_CONTENT_TYPES
    return looks_like_exercise(hit.text)


# Section names that hold term -> one-line-definition entries rather than
# explanation. Found 2026-09-18 chasing a live hallucination: asked where
# black soil is found, retrieval's top hit was a "शब्दावली" (glossary) chunk
# that correctly named the soil ("रेगर") but never said where -- the model
# kept the one true fact and invented the rest ("उत्तरी भारत", wrong) rather
# than admitting the gap. A prompt instruction not to guess was tried and
# failed (see tutor.py's GROUNDED_ANSWER_RULE history) -- it changed what the
# model invented, not whether it invented. This is the structural fix
# instead: a glossary entry answers "what is it called", never "where/why/
# how", so it carries exactly the shape that leaves a small model room to
# improvise. Matched on the heading, not the text -- unlike an exercise, a
# glossary line reads as fluent prose and has no shape of its own to detect.
_GLOSSARY_HEADINGS = re.compile(
    r"शब्दावली|glossary|key\s*terms?|keywords?", re.IGNORECASE
)


def looks_like_glossary(heading: str) -> bool:
    """True for a chunk sitting under a glossary / key-terms heading."""
    return bool(heading and _GLOSSARY_HEADINGS.search(heading))


def _looks_thin(hit: "Retrieved") -> bool:
    """An exercise or a glossary entry: correct, but rarely a full answer."""
    return is_exercise(hit) or looks_like_glossary(hit.heading)


# How much further away an explanation may be and still displace an exercise
# or glossary entry. Without a bound the reorder promotes anything that is
# not one of these: for "What are the types of motion?" it would have put
# "The SI unit of length is metre" (0.371) ahead of the activity on linear
# motion (0.364). In the science books an activity box is often where the
# content is; only an explanation that is about as relevant deserves its
# place.
_EXPLANATION_SLACK = 0.03


def _explanations_first(hits: Sequence[Retrieved]) -> List[Retrieved]:
    """Fused order, except a thin hit yields to a nearly-as-relevant explanation.

    An exercise often ranks well because it repeats the lesson's sentences as
    fill-in items -- "(क) उज्जैन की प्राचीन और ऐतिहासिक नगरी के बाहर ..." --
    but it hands the model a question where it needed an answer: asked what
    संज्ञा is, the model was given "(क) इस वाक्य में संज्ञा शब्द कौन-सा है?" and
    cited it. A glossary entry has the same problem from the other direction:
    it hands the model a correct one-line definition and nothing to answer
    "where/why/how" with. Neither is ever dropped: both already cleared the
    gate, and when nothing more explanatory is close, a thin hit still beats
    an unaided answer.

    Distances are the dense leg's; a lexical-only hit carries the 1.0
    placeholder and so can never displace anything.
    """
    ordered = list(hits)
    for i in range(len(ordered)):
        current = ordered[i]
        if not _looks_thin(current):
            continue
        for j in range(i + 1, len(ordered)):
            candidate = ordered[j]
            if (not _looks_thin(candidate)
                    and candidate.distance <= current.distance + _EXPLANATION_SLACK):
                ordered.insert(i, ordered.pop(j))
                break
    return ordered


def _pool_dense(searches: Sequence[Sequence[Retrieved]]) -> List[Retrieved]:
    """One dense list out of several searches: each passage at its best distance.

    A single search is returned untouched, so a question with no variant
    behaves exactly as it did before variants existed.
    """
    if len(searches) == 1:
        return list(searches[0])
    best: Dict[int, Retrieved] = {}
    for hits in searches:
        for hit in hits:
            held = best.get(hit.chunk_id)
            if held is None or hit.distance < held.distance:
                best[hit.chunk_id] = hit
    return sorted(best.values(), key=lambda h: h.distance)


def _interleave(rankings: Sequence[Sequence[Retrieved]]) -> List[Retrieved]:
    """Several ranked lists as one, by best rank: every list's first hit, then
    every list's second, skipping a passage already taken."""
    if len(rankings) == 1:
        return list(rankings[0])
    seen = set()
    pooled: List[Retrieved] = []
    for position in range(max((len(r) for r in rankings), default=0)):
        for ranking in rankings:
            if position < len(ranking) and ranking[position].chunk_id not in seen:
                seen.add(ranking[position].chunk_id)
                pooled.append(ranking[position])
    return pooled


async def retrieve(
    store: LibraryStore,
    question: str,
    *,
    grade: Optional[int],
    subject: Optional[str] = None,
    k: Optional[int] = None,
    language: Optional[str] = None,
    metrics: Optional[RetrievalMetrics] = None,
) -> List[Retrieved]:
    """The passages worth putting in front of the model, or [].

    Never raises. A tutor that answers from the model alone is a working
    tutor; one that 500s because the library is missing is not.

    Both legs are scoped to the lobby's grade, `subject` and medium
    (`language`). Subject used to be ignored on the theory that the breadcrumb
    already carried it -- true while each grade held one book, false the moment
    a grade holds two: bge-m3 is cross-lingual, so a Hindi question in a Class
    6 Hindi session can rank a Class 6 English Science passage first, and the
    breadcrumb is a few words against a whole passage of shared meaning.

    `metrics`, when supplied, is filled in place stage by stage. In place
    rather than returned because of the paragraph above: on every path where
    this function swallows a failure, the stages that did complete are exactly
    what identifies the one that did not, and a returned trace would be
    discarded along with the exception.
    """
    trace = metrics if metrics is not None else RetrievalMetrics()
    started = time.perf_counter()
    try:
        if not settings.rag_enabled:
            trace.abstain_reason = "retrieval disabled by configuration"
            return []
        if not store.is_open:
            trace.abstain_reason = "the textbook library is not open"
            return []
        if not question.strip():
            trace.abstain_reason = "empty question"
            return []

        trace.grade = grade
        trace.query_language = resolve_query_language(language, question)

        # The question as spoken is ALWAYS searched. When it holds a word the
        # library has never seen and there is a likely respelling (a speech-
        # recognition slip like जैब for जैव), that respelling is searched in
        # ADDITION and the two pools of candidates are merged -- never swapped
        # in for the original, so a wrong guess costs some extra candidates
        # rather than the right answer. See rag/spell.py.
        queries = [question]
        if settings.rag_spell_correct:
            alternative, fixes = spell.query_variant(question, store)
            if alternative:
                queries.append(alternative)
                trace.query_variant = alternative
                logger.info(
                    "Also searching a respelled variant: %s",
                    ", ".join("{} -> {}".format(f.original, f.corrected) for f in fixes),
                )

        # The store's model, not config's: after a re-embed cutover they differ.
        embed_started = time.perf_counter()
        vectors = [await embed_query(q, model=store.embedding_model) for q in queries]
        trace.embed_ms = elapsed_ms(embed_started)

        candidates = settings.rag_candidates
        trace.candidates = candidates

        dense_started = time.perf_counter()
        dense = _pool_dense([
            store.search(v, grade=grade, subject=subject, language=language, k=candidates)
            for v in vectors
        ])
        trace.dense_ms = elapsed_ms(dense_started)
        trace.dense_hits = len(dense)
        if dense:
            trace.best_distance = round(dense[0].distance, 4)
            # search() orders by distance, so the runner-up is simply the next
            # row. The gap between the two is the only confidence signal
            # available before the ranks replace the distances in fusion.
            if len(dense) > 1:
                trace.separation = round(dense[1].distance - dense[0].distance, 4)

        # The gate, before fusion. An empty dense leg here means the library
        # does not cover the question -- and BM25 is never consulted, because
        # it cannot tell the difference between coverage and coincidence.
        survivors, ceiling = gate_dense_hits(dense, trace.query_language)
        trace.ceiling = ceiling
        trace.gate_survivors = len(survivors)
        if trace.best_distance is not None:
            trace.headroom = round(ceiling - trace.best_distance, 4)
        if not survivors:
            trace.abstain_reason = _abstain_reason(dense, trace.query_language, ceiling)
            logger.info(
                "Nothing cleared the %s gate (ceiling %.2f, best %.3f); "
                "answering unaided.",
                trace.query_language,
                ceiling,
                dense[0].distance if dense else float("nan"),
            )
            return []

        match_queries = [m for m in (build_match_query(q) for q in queries) if m]
        trace.lexical_query = bool(match_queries)
        lexical_started = time.perf_counter()
        lexical = _interleave([
            store.search_lexical(
                m, grade=grade, subject=subject, language=language, k=candidates
            )
            for m in match_queries
        ])
        trace.lexical_ms = elapsed_ms(lexical_started)
        trace.lexical_hits = len(lexical)

        # Only passages that cleared the gate themselves, or sit immediately
        # beside one that did, are eligible. That keeps a definition split
        # across a chunk boundary retrievable without letting an unrelated
        # lexical hit ride in on a good one.
        eligible = {h.chunk_id for h in survivors}
        for hit in survivors:
            eligible.update(store.neighbours(hit.chunk_id))
        lexical = [h for h in lexical if h.chunk_id in eligible]
        trace.lexical_eligible = len(lexical)

        fused = _explanations_first(_rrf([survivors, lexical], k=settings.rag_rrf_k))
        trace.fused = len(fused)
        limit = k or settings.rag_top_k
        hits = fused[:limit]

        agreed = {h.chunk_id for h in survivors} & {h.chunk_id for h in lexical}
        trace.both_legs = sum(1 for h in hits if h.chunk_id in agreed)
        trace.returned = len(hits)
        trace.abstained = not hits
        if hits:
            trace.abstain_reason = ""
        return hits
    except StoreUnavailable as exc:
        trace.abstain_reason = "library unavailable: {}".format(exc.detail)
        logger.warning("Retrieval skipped: %s", exc.detail)
    except Exception as exc:  # noqa: BLE001
        trace.abstain_reason = "retrieval failed: {}".format(exc)
        logger.warning("Retrieval failed, answering without context: %s", exc)
    finally:
        trace.total_ms = elapsed_ms(started)
    return []


def _label(hit: Retrieved) -> str:
    pages = (
        "p. {}".format(hit.page_start)
        if hit.page_start == hit.page_end
        else "pp. {}-{}".format(hit.page_start, hit.page_end)
    )
    return " - ".join(filter(None, [hit.document_title, hit.heading, pages]))


# How to USE the excerpts now lives in the persona as `tutor.RETRIEVAL_RULE`,
# because the persona is the cached half of the prompt and this paragraph never
# changes. What stays here is only the excerpts themselves, which change every
# turn and are re-prefilled every turn no matter where they sit.
_EXCERPT_HEADER = "Textbook excerpts:"


def fit_to_budget(
    hits: Sequence[Retrieved],
    token_budget: Optional[int] = None,
    metrics: Optional[RetrievalMetrics] = None,
) -> List[Retrieved]:
    """As many whole passages as the budget allows, in order.

    k falls before a passage is cut. Three whole passages beat four half ones:
    a truncated passage loses exactly the part the model needed to answer from,
    and does it silently. This is why the budget is in tokens and the chunk
    bounds are in characters -- 2,000 characters of Devanagari is roughly three
    times the tokens of 2,000 characters of English, so a character budget
    would fit four English passages and overrun on four Hindi ones.
    """
    budget = token_budget or settings.rag_context_token_budget
    used = estimate_tokens(_EXCERPT_HEADER)
    kept: List[Retrieved] = []
    for hit in hits:
        cost = estimate_tokens("[{}] {}\n{}".format(len(kept) + 1, _label(hit), hit.text))
        if kept and used + cost > budget:
            break
        # The first passage goes in even if it alone exceeds the budget: a
        # tutor with one over-long excerpt is better than one with none, and
        # num_ctx is sized for that case.
        used += cost
        kept.append(hit)
    if len(kept) < len(hits):
        logger.info(
            "Context budget %d tokens: kept %d of %d passages (~%d tokens).",
            budget, len(kept), len(hits), used,
        )
    if metrics is not None:
        # `used` is what the model will actually re-read on CPU before it emits
        # a token, so it is the number to hold prefill_ms against. It counts
        # only the excerpts -- the system prompt and replayed history are on
        # top, which is why the budget sits well under num_ctx.
        metrics.context_tokens = used
        metrics.context_budget = budget
        metrics.dropped_over_budget = len(hits) - len(kept)
        metrics.returned = len(kept)
        metrics.abstained = not kept
    return kept


# A danda always ends a sentence; a Latin terminator needs whitespace after it
# so "3.14" and "p. 12" are not split mid-number. Same rule the frontend uses to
# decide when a sentence is safe to speak.
_SENTENCE_SPLIT = re.compile(r"(?<=[।॥])\s*|(?<=[.!?])\s+")
def trim_passage(text: str, query: str, max_tokens: int) -> str:
    """Cut one passage to its leading sentences, within a token cap.

    A retrieved chunk is sized for *embedding* quality -- 1,200 characters, so
    the vector has enough context to rank well. That is far more than the model
    needs to answer from, and on this CPU every one of those tokens is re-read
    before the student hears a word (measured 2026-09-09: ~22ms per prompt
    token, and three passages ran 538-617 tokens).

    So the chunk that goes into the *prompt* is not the chunk that was ranked:
    it is cut to its opening sentences, in order, until the cap is reached.
    Picking the sentences that share the most words with the question was
    tried first and broke an answer (see the comment in the body), which is why
    `query` is accepted but no longer used.
    """
    if max_tokens <= 0 or estimate_tokens(text) <= max_tokens:
        return text
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]
    if len(sentences) <= 1:
        return text

    # Keep the HEAD, in order, until the cap. Not the best-matching sentences.
    #
    # Selecting by overlap with the question was tried on 2026-09-09 and broke
    # an answer: asked about संज्ञा's types it kept "there are three main types"
    # -- which repeats the question's words -- and dropped the sentence naming
    # them, so the model invented them. Lexical scoring prefers topic sentences,
    # which are exactly the ones that carry no content.
    #
    # Taking the head has neither problem. Textbook paragraphs lead with the
    # definition and trail into elaboration, so the first sentences are the ones
    # worth paying for, and order is preserved so the passage still reads as
    # prose.
    kept: List[str] = []
    used = 0
    for sentence in sentences:
        cost = estimate_tokens(sentence)
        if kept and used + cost > max_tokens:
            break
        kept.append(sentence)
        used += cost
    return " ".join(kept)


def trim_passages(
    hits: Sequence[Retrieved], query: str, max_tokens: Optional[int] = None
) -> List[Retrieved]:
    """`trim_passage` over every hit. Cap of 0 disables trimming entirely."""
    cap = settings.rag_passage_token_cap if max_tokens is None else max_tokens
    if cap <= 0:
        return list(hits)
    return [replace(h, text=trim_passage(h.text, query, cap)) for h in hits]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def select_evidence(
    text: str, query: str, max_tokens: int, model: Optional[str] = None
) -> str:
    """Pick the sentence(s) most semantically relevant to the question, by
    embedding similarity -- NOT lexical keyword overlap.

    This is deliberately not the same thing as the "best-matching sentences"
    trim that was tried on 2026-09-09 and broke an answer (see trim_passage's
    own comment): that version scored sentences by shared WORDS with the
    question, which structurally favours a topic sentence that repeats the
    question's own vocabulary ("there are three types") over the sentence
    that actually carries the fact ("they are X, Y and Z") -- the model was
    then left with a claim and no content, and invented the content. Embedding
    similarity can recognise a sentence as relevant even when it shares no
    words with the question, which is the specific gap that caused that
    failure. Still a real, unverified risk in a new shape, not a solved one --
    treat groundedness and a spot-check of the actual answer as required
    evidence before trusting this, not just faster prefill.

    Falls back to trim_passage's safe head-taking behaviour if the embed call
    fails for any reason, since a too-long passage costs latency, but a wrong
    one costs correctness -- the two are not equally recoverable.
    """
    if max_tokens <= 0 or estimate_tokens(text) <= max_tokens:
        return text
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]
    if len(sentences) <= 1:
        return text
    try:
        # Query and sentences in one batched call -- bge-m3 needs no query/
        # document prefix distinction (see embeddings.py's _needs_prefix), so
        # embedding them together costs one round-trip instead of two.
        vectors = await embed_documents([query] + sentences, model=model)
    except Exception as exc:  # noqa: BLE001 - fall back, never break the turn
        logger.warning("Evidence extraction embed failed, falling back to head-trim: %s", exc)
        return trim_passage(text, query, max_tokens)
    query_vector, sentence_vectors = vectors[0], vectors[1:]
    scored = sorted(
        range(len(sentences)),
        key=lambda i: _cosine(query_vector, sentence_vectors[i]),
        reverse=True,
    )
    selected: set = set()
    used = 0
    for idx in scored:
        cost = estimate_tokens(sentences[idx])
        if selected and used + cost > max_tokens:
            continue  # doesn't fit alongside what's already picked; try the next-best
        selected.add(idx)
        used += cost
        if used >= max_tokens:
            break
    if not selected:
        selected.add(scored[0])  # keep the single best even if it alone exceeds the cap
    # Original passage order, not score order, so the result still reads as prose.
    return " ".join(sentences[i] for i in sorted(selected))


async def select_evidence_for_hits(
    hits: Sequence[Retrieved], query: str, max_tokens: int, model: Optional[str] = None
) -> List[Retrieved]:
    """`select_evidence` over every hit. Cap of 0 disables it entirely."""
    if max_tokens <= 0:
        return list(hits)
    out = []
    for h in hits:
        text = await select_evidence(h.text, query, max_tokens, model=model)
        out.append(replace(h, text=text))
    return out


def build_context_block(hits: Sequence[Retrieved]) -> str:
    """Format retrieved chunks for the prompt.

    Each excerpt is labelled with its source so the model can point a student
    at the page, and the instruction is deliberately permissive: a small model
    told to answer *only* from context refuses far too often, which reads to a
    student as the tutor being broken.
    """
    if not hits:
        return ""
    parts = [
        "[{}] {}\n{}".format(i, _label(h), h.text) for i, h in enumerate(hits, start=1)
    ]
    return _EXCERPT_HEADER + "\n\n" + "\n\n".join(parts)


# Keyed by (grade, subject, language) -- the same three things the student
# picks in the lobby, because those decide which book gets pinned. One entry
# per selection: the block is static for a given selection, and rebuilding it
# per turn would cost a full table read for no reason.
#
# Keying on all three also means switching subject or medium mid-session picks
# up a different pinned block rather than silently reusing the old one.
_PinKey = Tuple[Optional[int], str, str]
_PINNED: Dict[_PinKey, Optional[Tuple[str, List[Retrieved]]]] = {}


def pinned_context(
    store,
    *,
    grade: Optional[int] = None,
    subject: Optional[str] = None,
    language: Optional[str] = None,
) -> Optional[Tuple[str, List[Retrieved]]]:
    """The whole corpus as one fixed prompt block, or None if it will not fit.

    Why this exists at all: Ollama reuses a cached KV prefix only against the
    request that immediately preceded it. Per-question retrieval puts different
    passages in every prompt, so consecutive prompts diverge right after the
    persona and NOTHING is ever reused -- measured 2026-09-09 at 15-26s of
    prefill per turn, re-reading the same 568-token persona every time.

    Pin the corpus instead and the block is byte-identical every turn, so each
    turn extends the last and the cache actually holds. Same model, same box:
    prefill fell to 1.6-3.1s.

    This is only honest while the corpus is small. Above the budget it returns
    None and the caller falls back to per-question retrieval, because a book
    that does not fit cannot be pinned and pretending otherwise would silently
    truncate the prompt.
    """
    budget = settings.rag_pin_corpus_max_tokens
    if budget <= 0:
        return None
    key: _PinKey = (grade, (subject or "").lower(), (language or "").lower())
    if key in _PINNED:
        return _PINNED[key]

    try:
        hits = store.all_chunks(grade=grade, subject=subject, language=language)
    except Exception as exc:  # StoreUnavailable, or a corpus that predates this
        logger.info("Corpus pinning unavailable (%s); using per-question retrieval.", exc)
        _PINNED[key] = None
        return None

    if not hits:
        _PINNED[key] = None
        return None

    block = build_context_block(hits)
    cost = estimate_tokens(block)
    if cost > budget:
        logger.info(
            "Corpus is %d tokens, over the %d-token pin budget: using per-question "
            "retrieval instead.", cost, budget,
        )
        _PINNED[key] = None
        return None

    logger.info(
        "Pinned %d chunks (~%d tokens) for grade=%s subject=%s medium=%s. "
        "Retrieval is skipped; the block is identical every turn so Ollama "
        "reuses its KV cache.",
        len(hits), cost, grade, subject or "any", language or "any",
    )
    _PINNED[key] = (block, hits)
    return _PINNED[key]


def reset_pinned_cache() -> None:
    """Forget what is derived from the corpus: the pinned block and the spelling
    vocabulary. Call after ingestion or a delete changes it."""
    _PINNED.clear()
    spell.invalidate()


def citations(hits: Sequence[Retrieved]) -> List[dict]:
    """Source list for the UI, including the excerpt actually shown to the model.

    The text is the same string that went into the prompt, not a fresh fetch
    -- so what a student or teacher reads in the citation panel is provably
    what the model was grounded on, not a claim about it.
    """
    return [
        {
            "title": h.document_title,
            "heading": h.heading,
            "page_start": h.page_start,
            "page_end": h.page_end,
            "grade": h.grade,
            "subject": h.subject,
            "distance": round(h.distance, 4),
            "text": h.text,
        }
        for h in hits
    ]
