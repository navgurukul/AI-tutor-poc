"""Measuring a turn: where the time went, and how good the retrieval was.

The models themselves live in `app.schemas` -- they are part of the API
contract, they are returned verbatim to the UI, and a second parallel set of
dataclasses here would be one more place to forget a field. This module holds
only the behaviour: the clock, the log line, and the one metric that has to be
computed rather than observed.

Two questions get confused whenever an answer is slow or wrong, and they have
different fixes:

  - **Where did the time go?** Retrieval is milliseconds; the model is seconds.
    The flat scan measures ~10ms and the query embedding ~100-300ms, against a
    prefill that runs into the thousands. So the latency RAG actually costs is
    not the search -- it is that every retrieved passage is re-read by the
    model on CPU, in full, before the first token appears. That makes
    `prefill_ms` against `context_tokens` the pair worth watching, and it is
    why the two are reported side by side rather than as one response time.

  - **Did retrieval find the right thing?** There is no golden answer at query
    time, so nothing here measures correctness -- `scripts/evaluate_retrieval.py`
    against the golden set remains the only thing that does. What is available
    live are reference-free proxies that move with it: how much room the best
    hit had against its ceiling, how far the runner-up trails it, and whether
    both legs agreed. Read them as a reason to go and measure, not as a
    measurement.

Nothing here issues a model call. An LLM judge would answer "was that answer
any good?" far better and cost another full generation on the same CPU -- which
is the thing being reduced.
"""

import re
import time
from typing import Optional, Sequence, Tuple

from app.schemas import TurnMetrics
from app.services.rag.query import dominant_script
from app.services.rag.store import Retrieved


def elapsed_ms(since: float) -> float:
    """Milliseconds since a `time.perf_counter()` mark, rounded for reporting."""
    return round((time.perf_counter() - since) * 1000.0, 1)


# --------------------------------------------------------------------------
# Groundedness
# --------------------------------------------------------------------------
# Words carried by grammar rather than by meaning. Matching on these lifts
# every answer's score by roughly the same amount, which is worse than useless:
# it compresses the range the number has to be read across. English only, for
# the same reason the FTS5 handling is -- a Devanagari list would need
# measuring first, and the trigram overlap below is far less sensitive to
# function words than whole-word matching would be.
_FILLER = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "for",
    "from", "has", "have", "in", "is", "it", "its", "of", "on", "or", "that",
    "the", "their", "them", "then", "there", "these", "they", "this", "to",
    "was", "were", "which", "with", "you", "your",
}

_WORDS = re.compile(r"[\wऀ-ॿ]+", re.UNICODE)

# Below this many trigrams the ratio is noise, not a measurement. A two-word
# reply has a handful of trigrams and they are all common ones, so it scores
# 1.00 against any passage at all -- which is exactly what the page-load
# warm-up (a deliberate one-token generation) was reporting.
_MIN_TRIGRAMS = 8


def _trigrams(text: str) -> set:
    """Character trigrams of the content words in `text`.

    Trigrams rather than whole words, and for exactly the reason the FTS5 index
    uses `tokenize='trigram'`: Devanagari inflects heavily, so कोशिका on the
    page and कोशिकाओं in the answer are the same idea and never the same token.
    Trigrams share the stem. English gets the same tolerance for free (cell /
    cells), which keeps one number roughly comparable across languages instead
    of two that are not comparable at all.
    """
    grams = set()
    for word in _WORDS.findall(text.lower()):
        if word in _FILLER or word.isdigit():
            continue
        if len(word) <= 3:
            grams.add(word)
            continue
        for i in range(len(word) - 2):
            grams.add(word[i : i + 3])
    return grams


def groundedness(
    answer: str, hits: Sequence[Retrieved]
) -> Tuple[Optional[float], str]:
    """How much of the answer's wording traces to its passages: (score, note).

    The score is 0-1, or None with a note saying why it was not scored. A note
    rather than a zero, because the three reasons a zero could appear here mean
    completely different things and only one of them is a problem.

    What it is for: the citation list is the most dangerous thing this app
    renders. A reply that ignored the excerpts and answered from the model's
    weights still gets a chapter and a page number attached, and to a student
    that page number reads as proof. A low score is that failure surfacing as a
    number, per turn, for free.

    What it is not: a correctness check. It measures overlap of wording, so a
    fluent paraphrase scores lower than a clumsy quotation, and a confident
    falsehood assembled from words that do appear on the page scores high.
    Treat a low score as a reason to read the excerpt; never a high one as a
    pass.
    """
    if not hits:
        # Not ungrounded -- a different kind of answer. Scoring it zero would
        # drag every average down for the case the gate got right.
        return None, "answered without the library"

    # The cross-lingual case, and the one that makes this metric lie. A Hindi
    # answer written from an English page is the whole point of the bge-m3
    # work, and it shares no wording with its source by construction -- so it
    # scores 0.00 and reads as "the model ignored the passages" when the model
    # did exactly what it was asked. Any measurement that would work here
    # (translate, or embed both sides) costs a model call, which is the thing
    # being optimised. Declining to score is the honest option.
    answer_script = dominant_script(answer)
    context = "\n".join(h.text for h in hits)
    context_script = dominant_script(context)
    if answer_script != context_script:
        return None, "answer is {}, passages are {} -- wording cannot be compared".format(
            answer_script, context_script
        )

    answer_grams = _trigrams(answer)
    context_grams = _trigrams(context)
    if len(answer_grams) < _MIN_TRIGRAMS or not context_grams:
        return None, "answer too short to score"
    return round(len(answer_grams & context_grams) / float(len(answer_grams)), 3), ""


# --------------------------------------------------------------------------
# The log line
# --------------------------------------------------------------------------
def format_turn(metrics: TurnMetrics, label: str = "turn") -> str:
    """One line per turn, so latency can be read out of the log without the UI.

    Ordered as the turn happens, so scanning the column shows which stage moved
    after a change rather than only that the total did.

    `label` distinguishes a student's question from the page-load warm-up,
    which is a real request costing real prefill but is not a turn anyone
    waited on. Averaging the two together is how a warm-up's cost gets
    attributed to the tutor.
    """
    r = metrics.retrieval

    def num(value: Optional[float], spec: str) -> str:
        return format(value, spec) if value is not None else "-"

    return (
        "{label} {total:.0f}ms | retrieval {retrieval:.0f}ms "
        "(embed {embed:.0f} dense {dense:.0f} lex {lex:.0f}) "
        "-> {returned} passages / {ctx} ctx tokens{carried} | ttft {ttft} | "
        "prefill {prefill}ms ({ptok} tok) decode {decode}ms ({ctok} tok"
        "{tps}){retry} | {lang} best {best} headroom {headroom} "
        "grounded {grounded}"
    ).format(
        label=label,
        total=metrics.total_ms,
        retrieval=metrics.retrieval_ms,
        embed=r.embed_ms,
        dense=r.dense_ms,
        lex=r.lexical_ms,
        returned=r.returned,
        ctx=r.context_tokens,
        # Only printed when it fired, so the rate is visible in a scan of the
        # log rather than being a "no" on every line.
        carried=" [carried]" if r.query_carried else "",
        ttft=num(metrics.ttft_ms, ".0f") + ("ms" if metrics.ttft_ms is not None else ""),
        prefill=metrics.prefill_ms,
        ptok=metrics.prompt_tokens,
        decode=metrics.decode_ms,
        ctok=metrics.completion_tokens,
        # Ollama divides the token count by a nanosecond duration, so a
        # one-token generation reports something like 1000000.0 tok/s. That is
        # not a fast turn, it is a rate with no denominator worth dividing by.
        tps=(
            ", {:.1f} tok/s".format(metrics.tokens_per_second)
            if metrics.completion_tokens > 1
            else ""
        ),
        # Only printed when it happened, so it stands out in a scan of the log
        # instead of being a zero on every line.
        retry=(
            " | socratic retry {:.0f}ms".format(metrics.retry_ms)
            if metrics.retry_ms
            else ""
        ),
        lang=r.query_language or "?",
        best=num(r.best_distance, ".3f"),
        headroom=num(r.headroom, "+.3f"),
        grounded=(
            num(metrics.groundedness, ".2f")
            if metrics.groundedness is not None
            else "n/a ({})".format(metrics.groundedness_note or "not measured")
        ),
    )
