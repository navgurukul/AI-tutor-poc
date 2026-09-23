"""Stage orchestration, and the report an upload gets back.

Eight stages run over one `Document` that each of them annotates in place:

    extract -> layout -> detect -> repair -> classify -> normalize
            -> chunk -> validate

Three orderings are load-bearing and easy to get wrong.

**Repair before classify.** Classification reads the repaired text. A legacy
page classified on its raw bytes has no headings at all -- only Latin noise
that looks like prose. Here repair happens inside extraction (span-level, by
font name), which puts it earlier still.

**Classify before normalize.** Normalization treats tables differently from
paragraphs: prose gets its soft-wrapped lines rejoined, a table keeps them,
because in a table those line breaks *are* the row boundaries.

**Detect before repair, but language recounted after.** Detection runs on the
extracted text; the document's language summary is recomputed once conversion
has finished, or a Hindi textbook is filed as English because the only readable
words in it were on the copyright page.

Nothing here touches Ollama or the database. `analyze()` is therefore the safe
first look at an unfamiliar PDF, which is what the CLI uses.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from app.config import settings

from . import classify, detect, extract, furniture, layout, normalize, validate
from .chunk import chunk_document
from .model import Chunk, Document

logger = logging.getLogger(__name__)

PdfExtractionError = extract.PdfExtractionError


def _run_layout(document: Document) -> Dict[str, int]:
    """Stage 2 -- columns and reading order, per page."""
    counts = {"single_column": 0, "two_column": 0}
    for page in document.pages:
        layout.analyze_layout(page)
        if page.column_count > 1:
            counts["two_column"] += 1
        else:
            counts["single_column"] += 1
    return counts


def analyze(data: bytes, meta: Dict[str, Any] | None = None) -> Tuple[Document, Dict[str, Any]]:
    """Run stages 1-6 and return the document plus a per-stage report.

    Touches neither Ollama nor the database.
    """
    meta = dict(meta or {})
    report: Dict[str, Any] = {}

    document = extract.extract_document(data, meta)
    report["extract"] = {
        "pages": document.page_count,
        "blocks": sum(len(page.blocks) for page in document.pages),
    }

    report["layout"] = _run_layout(document)
    report["detect"] = detect.detect_document(document)
    report["classify"] = classify.classify_document(document)

    normalize.normalize_document(document)

    # Furniture after normalization, because the stem of a running head is
    # taken from the settled text, and before chunking, because a running head
    # the classifier has called a heading becomes a SECTION and is then
    # stamped on every passage beneath it as the breadcrumb.
    marked, inline = furniture.run(document)
    report["furniture"] = {"blocks": marked, "inline_lines": inline}

    # Language is recounted now that normalization has settled the text, for
    # the reason in this module's docstring. `summarize`, NOT
    # `detect_document`: re-running per-block detection here would reset every
    # block's normalized_text to the raw extraction and undo stages 4 and 6.
    report["detect"] = detect.summarize(document)

    return document, report


def build_chunks(data: bytes, meta: Dict[str, Any] | None = None) -> Tuple[List[Chunk], Dict[str, Any]]:
    """Run the whole pipeline. Returns (accepted chunks, report).

    Rejected chunks are counted in the report but never returned: an unusable
    chunk in the index is worse than a missing one, because retrieval will
    surface it confidently and the student has no way to tell.
    """
    document, report = analyze(data, meta)

    chunks = chunk_document(document)
    report["chunk"] = {
        "total": len(chunks),
        "by_type": _count_by(chunks, "content_type"),
        "tokens": _token_summary(chunks),
        "target_tokens": settings.rag_chunk_target_tokens,
    }

    report["validate"] = validate.validate_chunks(chunks)
    accepted = [chunk for chunk in chunks if chunk.valid]

    logger.info(
        "Ingestion pipeline: %d pages -> %d blocks -> %d chunks -> %d accepted "
        "(%s two-column pages, verdict %s)",
        report["extract"]["pages"],
        report["extract"]["blocks"],
        len(chunks),
        len(accepted),
        report["layout"]["two_column"],
        report["validate"]["verdict"]["reason"],
    )
    return accepted, report


def _count_by(chunks: List[Chunk], field: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for chunk in chunks:
        key = str(getattr(chunk, field))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def _token_summary(chunks: List[Chunk]) -> Dict[str, Any]:
    """Chunk sizes against the prompt cap.

    `over_cap` is the number that matters and the reason this summary exists:
    a chunk larger than `rag_passage_token_cap` is one the model will only
    ever see the opening of. It should be near zero. If it climbs, chunking
    and the prompt budget have drifted apart again.
    """
    if not chunks:
        return {"median": 0, "max": 0, "over_cap": 0, "cap": settings.rag_passage_token_cap}
    sizes = sorted(chunk.token_estimate for chunk in chunks)
    cap = settings.rag_passage_token_cap
    return {
        "median": sizes[len(sizes) // 2],
        "p90": sizes[int(0.9 * (len(sizes) - 1))],
        "max": sizes[-1],
        "cap": cap,
        "over_cap": sum(1 for size in sizes if cap > 0 and size > cap),
    }


def warning_for(report: Dict[str, Any]) -> str:
    """A sentence for the setup page, or "" when the document looks fine.

    Separate from the verdict: a verdict refuses the file, a warning stores it
    and says why answers from it may be poor. An upload is only refused when
    the text layer is genuinely unreadable, because the person uploading
    usually has no other copy of the book and a refusal just moves the problem
    to them.
    """
    issues = report.get("validate", {}).get("issues", {})
    total = report.get("validate", {}).get("total", 0) or 1

    fragmented = issues.get("fragmented_text", 0) / total
    if fragmented >= 0.1:
        return (
            "{:.0%} of this book extracted as loose characters rather than words; "
            "answers from those pages may be poor."
        ).format(fragmented)

    legacy_share = report.get("detect", {}).get("unconverted_legacy_share", 0.0)
    if legacy_share >= 0.1:
        return (
            "{:.0%} of this book is in an old Hindi font that could not be "
            "converted; answers from it may be poor."
        ).format(legacy_share)

    over_cap = report.get("chunk", {}).get("tokens", {}).get("over_cap", 0)
    chunk_total = report.get("chunk", {}).get("total", 0)
    if chunk_total and over_cap / chunk_total >= 0.5:
        return (
            "{} of {} passages are larger than the prompt can carry; the tutor "
            "will only see the opening of them."
        ).format(over_cap, chunk_total)

    return ""
