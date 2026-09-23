"""Stage 3 -- language, script and encoding, per block.

The question this stage answers is not "what language is this?" but "can the
text be trusted as extracted?". A block of Latin characters is either English
or a legacy Devanagari font pretending to be English, and telling those apart
is the whole job.

This is a reduced version of the upstream stage. Upstream owned the legacy
conversion itself and so had to decide, per block, whether to run a converter
over it. Here the conversion has already happened: `extract.convert_legacy_spans`
rewrites Chanakya/KrutiDev/DevLys text during extraction, by font name, which
is decisive and needs no scoring (EXP-006). What is left for this stage is the
case that conversion cannot reach -- a legacy font whose NAME is not in the
registry, such as NeoMitra. Its text arrives as Latin gibberish that reads as
confident English, embeds cleanly, and matches nothing a student ever asks.

So the detector's one real job here is to mark that text `legacy_devanagari`,
which is an issue `validate.py` rejects on. Everything else it records is
descriptive.

Evidence is kept alongside the decision so a wrong call can be explained
afterwards rather than merely observed.
"""

from __future__ import annotations

import re
from typing import Any

from .model import Block, Document, Page
from .scripts import dominant_script, merge_stats, ratios, text_stats

# Very common Hindi function words as they appear when a legacy Devanagari
# font is read as Latin. Individually weak -- "ds" and "ls" occur in English
# too -- but a block full of them is decisive.
LEGACY_PATTERNS = (
    r"\bHkkjr\b", r"\bd\{kk\b", r"\bls\b", r"\besa\b", r"\bvkSj\b",
    r"\bds\b", r"\bdh\b", r"\bdk\b", r"\bgS\b", r"\bgs\b", r"\bfu\b",
    r"\biz\b", r"\bfoKku\b", r"\bHkwxksy\b", r"\bfd\b", r"\bij\b",
    r"\bughaa?\b", r"\bfy\b", r"\bdj\b", r"\bgksrk\b",
)

_LEGACY_RE = re.compile("|".join(LEGACY_PATTERNS))

# A block must clear this many legacy-marker hits before it is called legacy
# rather than English. Set against whole blocks, not pages, because this
# pipeline classifies per block -- a caption in a real legacy book is short and
# would never reach a page-sized threshold.
LEGACY_SCORE_THRESHOLD = 3

# Below this many characters there is not enough text to judge anything.
MIN_USABLE_CHARS = 20

# Latin letters are what a mis-read legacy font produces. A block that is
# mostly Devanagari already converted cleanly and is not a candidate.
_MIN_LATIN_RATIO_FOR_LEGACY = 0.5


def legacy_marker_count(text: str) -> int:
    return len(_LEGACY_RE.findall(text))


def classify_text(text: str) -> dict[str, Any]:
    """Language, script and encoding for one piece of text, with evidence."""
    stats = text_stats(text)
    proportions = ratios(stats)
    script = dominant_script(stats)
    markers = legacy_marker_count(text)

    evidence: dict[str, Any] = {
        "chars": stats["total_chars"],
        "legacy_markers": markers,
        **proportions,
    }

    if stats["total_chars"] < MIN_USABLE_CHARS:
        return {
            "language": "unknown",
            "script": script,
            "encoding": "unknown",
            "evidence": {**evidence, "reason": "too_short"},
        }

    # An unregistered legacy font: Latin-looking text dense in the function
    # words Devanagari collapses into. Marked, never guessed at -- there is no
    # table for it, so the honest outcome is to refuse the text downstream.
    if (
        markers >= LEGACY_SCORE_THRESHOLD
        and proportions["latin_ratio"] >= _MIN_LATIN_RATIO_FOR_LEGACY
    ):
        return {
            "language": "hi",
            "script": "legacy_devanagari",
            "encoding": "legacy",
            "evidence": {**evidence, "reason": "legacy_markers_in_latin_text"},
        }

    if script == "Devanagari":
        # Devanagari, but Hindi or Marathi? Nothing in the script says, and
        # this pipeline does not need to know: the medium is a field the
        # person uploading the book already filled in.
        return {
            "language": "hi",
            "script": script,
            "encoding": "unicode",
            "evidence": {**evidence, "reason": "devanagari_script"},
        }

    if script == "Latin":
        return {
            "language": "en",
            "script": script,
            "encoding": "unicode",
            "evidence": {**evidence, "reason": "latin_script"},
        }

    return {
        "language": "unknown",
        "script": script,
        "encoding": "unknown",
        "evidence": {**evidence, "reason": "no_dominant_script"},
    }


def detect_block(block: Block) -> dict[str, Any]:
    result = classify_text(block.text)
    block.language = result["language"]
    block.script = result["script"]
    block.encoding = result["encoding"]
    # The working text starts as the extracted text; normalize.py rewrites it
    # in place at stage 6.
    #
    # Seeded ONLY when empty. This stage is deliberately re-runnable -- the
    # language summary is recomputed once normalization has settled the text
    # -- and an unconditional assignment here made the second run silently
    # undo the first's work: normalized_text went back to the raw extraction,
    # taking the rejoined soft wraps and the Devanagari repairs with it.
    #
    # The symptom was a library whose every chunk ended mid-sentence, at the
    # printed LINE break, which is unanswerable. Use `summarize()` when only
    # the document totals are wanted.
    if not block.normalized_text:
        block.normalized_text = block.text
    return result


def detect_page(page: Page) -> dict[str, Any]:
    per_block = [detect_block(block) for block in page.text_blocks]
    page.stats.update(text_stats(page.text))
    page.detection = classify_text(page.text)
    return {"blocks": per_block, "page": page.detection}


def detect_document(document: Document) -> dict[str, Any]:
    """Detect every page, then summarise the document from the result."""
    for page in document.pages:
        detect_page(page)
    return summarize(document)


def summarize(document: Document) -> dict[str, Any]:
    """Recompute the document-level summary from what the blocks already say.

    Separate from `detect_document` because the summary has to be recomputed
    after normalization -- a Hindi textbook detected before legacy conversion
    is filed as English, since the only readable words in it were on the
    copyright page -- while re-running per-block detection at that point would
    throw normalization away.
    """
    merged = merge_stats([page.stats for page in document.pages])
    languages: dict[str, int] = {}
    scripts: dict[str, int] = {}
    for page in document.pages:
        for block in page.text_blocks:
            chars = len(block.text)
            languages[block.language] = languages.get(block.language, 0) + chars
            scripts[block.script] = scripts.get(block.script, 0) + chars

    total = sum(languages.values()) or 1
    legacy_chars = scripts.get("legacy_devanagari", 0)

    document.summary = {
        "stats": merged,
        "ratios": ratios(merged),
        "languages": dict(sorted(languages.items(), key=lambda kv: kv[1], reverse=True)),
        "scripts": dict(sorted(scripts.items(), key=lambda kv: kv[1], reverse=True)),
        "dominant_language": max(languages, key=lambda k: languages[k]) if languages else "unknown",
        # The share that arrived in a legacy font nothing could convert. This
        # is what turns into the upload warning; see `pipeline.verdict`.
        "unconverted_legacy_share": round(legacy_chars / total, 4),
        "legacy_spans_converted": sum(
            int(page.stats.get("legacy_spans", 0)) for page in document.pages
        ),
    }
    return document.summary
