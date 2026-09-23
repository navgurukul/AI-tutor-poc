"""
Stage 1 -- PDF ingestion and structure analysis.

PyMuPDF gives us glyphs with positions. This module turns that into
the intermediate document model: pages, blocks, lines, spans, fonts
and bounding boxes.

It deliberately does not:
  - detect language
  - convert legacy encodings
  - OCR
  - chunk or embed

Those are later stages, and keeping them out of here is what lets
the detector see the *raw* extraction rather than something already
cleaned up underneath it.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import pymupdf

from app.services.rag import legacy_hindi

from .equations import Fragment, Rule, assemble_fractions, find_rules, render_line
from .model import Block, Document, Line, Page, Span


class PdfExtractionError(Exception):
    """Raised when a file cannot be read as a PDF at all.

    Re-declared here rather than imported from `pdf_text` so this package has
    no dependency on the module it replaces. `pdf_text.PdfExtractionError` is
    kept as an alias while both paths exist.
    """

# PyMuPDF span flag bits.
_FLAG_ITALIC = 1 << 1
_FLAG_BOLD = 1 << 4

# PyMuPDF block types.
_BLOCK_TEXT = 0
_BLOCK_IMAGE = 1

# Subset-embedded fonts arrive as "ABCDEF+RealName".
_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")


def base_font_name(font: str) -> str:
    """Strip the subset prefix so font names can be matched."""
    return _SUBSET_PREFIX.sub("", font or "")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def slugify(value: str) -> str:
    """A filesystem-ish name turned into a stable identifier fragment."""
    value = unicodedata.normalize("NFKD", value)
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE).strip().lower()
    value = re.sub(r"[\s_-]+", "-", value)
    return value.strip("-") or "document"


def convert_legacy_spans(raw_page: dict) -> int:
    """Rewrite legacy-font span text to Unicode, in place. Returns spans hit.

    Done here, on the raw dict, rather than as a later repair stage, because
    everything downstream -- `_build_span`, `render_line`, the fraction
    assembler -- reads these same span texts, and a stage that converted after
    them would leave three different readings of one page in play.

    Consecutive legacy spans in a line are converted as ONE run. The i-matra
    and the reph are typed on the other side of the cluster they belong to, so
    a word can straddle a span boundary and converting span by span splits it
    mid-syllable. The whole run's converted text is assigned to the run's first
    span and the rest are emptied -- their geometry is lost, which costs
    nothing: column detection reads block boxes, and the classifier reads the
    block's max size and weight, both of which survive on the first span.
    """
    converted = 0
    for raw_block in raw_page.get("blocks", []):
        if raw_block.get("type") != _BLOCK_TEXT:
            continue
        for raw_line in raw_block.get("lines", []):
            run: list[dict] = []

            def flush(run: list[dict]) -> int:
                if not run:
                    return 0
                joined = "".join(span.get("text", "") for span in run)
                run[0]["text"] = legacy_hindi.to_unicode(joined)
                for span in run[1:]:
                    span["text"] = ""
                return len(run)

            for raw_span in raw_line.get("spans", []):
                if legacy_hindi.is_legacy_font(raw_span.get("font", "")):
                    run.append(raw_span)
                    continue
                converted += flush(run)
                run = []
            converted += flush(run)
    return converted


def _build_span(raw: dict) -> Span | None:
    text = raw.get("text", "")
    if not text:
        return None

    flags = raw.get("flags", 0)
    font = raw.get("font", "")

    return Span(
        text=text,
        font=font,
        size=round(float(raw.get("size", 0.0)), 2),
        bbox=tuple(raw.get("bbox", (0.0, 0.0, 0.0, 0.0))),
        # Some generators encode weight only in the name, not the flags.
        bold=bool(flags & _FLAG_BOLD) or "bold" in font.lower(),
        italic=bool(flags & _FLAG_ITALIC) or "italic" in font.lower(),
    )


def _build_text_block(
    index: int,
    raw: dict,
    rules: list[Rule] | None = None,
) -> Block | None:
    lines: list[Line] = []
    rendered: list[str] = []

    for raw_line in raw.get("lines", []):
        raw_spans = raw_line.get("spans", [])
        spans = [
            span
            for span in (_build_span(raw_span) for raw_span in raw_spans)
            if span is not None
        ]
        if not spans:
            continue

        lines.append(
            Line(spans=spans, bbox=tuple(raw_line.get("bbox", (0.0, 0.0, 0.0, 0.0))))
        )

        # Mathematical normalization at the span level: superscripts
        # and subscripts are geometry, and this is the last point at
        # which that geometry exists. Fractions span several blocks,
        # so they are assembled per page below.
        rendered.append(render_line(raw_spans))

    if not lines:
        return None

    # Line breaks inside a block are preserved here. Paragraph
    # reflow is normalize.py's job, and it needs to see them.
    text = "\n".join(part for part in rendered if part.strip())
    if not text.strip():
        return None

    return Block(
        index=index,
        kind="text",
        bbox=tuple(raw.get("bbox", (0.0, 0.0, 0.0, 0.0))),
        lines=lines,
        text=text,
    )


def _assemble_page_fractions(
    raw_page: dict,
    rules: list[Rule],
    page_width: float,
) -> dict[int, Block | None]:
    """
    Rebuild fractions that PyMuPDF split across blocks.

    A displayed equation comes back as one block per glyph, so the
    numerator and denominator of `Q/4πε₀r` are separate blocks
    either side of a rule. Matching them needs every span on the
    page, not one block's worth.

    Returns a map from block index to its replacement: the lowest
    index in each fraction carries the reconstructed text, the rest
    map to None and are dropped.
    """
    if not rules:
        return {}

    fragments: list[Fragment] = []
    for index, raw_block in enumerate(raw_page.get("blocks", [])):
        if raw_block.get("type") != _BLOCK_TEXT:
            continue
        for raw_line in raw_block.get("lines", []):
            for span in raw_line.get("spans", []):
                if not span.get("text", "").strip():
                    continue
                x0, y0, x1, y1 = span["bbox"]
                fragments.append(
                    Fragment(
                        block=index,
                        text=span["text"],
                        x0=x0, y0=y0, x1=x1, y1=y1,
                        size=float(span.get("size", 0.0)),
                    )
                )

    replacements: dict[int, Block | None] = {}

    for blocks, text, box in assemble_fractions(fragments, rules, page_width):
        owner = min(blocks)
        replacements[owner] = Block(
            index=owner,
            kind="text",
            bbox=box,
            lines=[],
            text=text,
            content_type="formula",
        )
        for other in blocks:
            if other != owner:
                replacements[other] = None

    return replacements


def extract_page(page_number: int, page) -> Page:
    """Extract one PDF page into the document model."""
    rect = page.rect
    result = Page(
        number=page_number,
        width=round(float(rect.width), 2),
        height=round(float(rect.height), 2),
    )

    raw_page = page.get_text("dict")
    result.stats["legacy_spans"] = convert_legacy_spans(raw_page)
    rules = find_rules(page)
    fractions = _assemble_page_fractions(raw_page, rules, result.width)

    for index, raw_block in enumerate(raw_page.get("blocks", [])):
        block_type = raw_block.get("type")

        if block_type == _BLOCK_TEXT:
            if index in fractions:
                # This block's glyphs were consumed by a fraction.
                # The first one carries the whole reconstruction;
                # the rest are dropped.
                block = fractions[index]
                if block is not None:
                    result.blocks.append(block)
                continue

            block = _build_text_block(index, raw_block, rules)
            if block is not None:
                result.blocks.append(block)

        elif block_type == _BLOCK_IMAGE:
            # Kept without pixel data: the classifier only needs the
            # box, to tell whether nearby text is a caption.
            result.blocks.append(
                Block(
                    index=index,
                    kind="image",
                    bbox=tuple(raw_block.get("bbox", (0.0, 0.0, 0.0, 0.0))),
                    content_type="image",
                )
            )

    return result


def extract_document(data: bytes, meta: dict | None = None) -> Document:
    """Extract PDF bytes into a Document. Raises PdfExtractionError.

    Bytes rather than a path because that is what the upload endpoint already
    holds: `IngestionService` reads the file once, hashes it for the duplicate
    check, and hands the same buffer on. Taking a path here would mean writing
    the upload to a temporary file purely to read it back.

    `meta` carries caller-supplied bibliographic fields (subject, grade,
    chapter, ...) straight through to the chunk metadata.
    """
    meta = dict(meta or {})
    sha = hashlib.sha256(data).hexdigest()

    display_name = meta.get("file_name") or "document.pdf"
    stem = Path(display_name).stem

    document = Document(
        # A content hash in the id keeps re-ingests of an edited file
        # from silently colliding with the previous version.
        document_id=meta.get("document_id") or f"{slugify(stem)}-{sha[:8]}",
        file_name=display_name,
        sha256=sha,
        meta=meta,
    )

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise PdfExtractionError(
            "Could not read this file as a PDF ({}).".format(exc)
        ) from exc

    try:
        # An empty password unlocks the common "no printing" case; a real
        # password is a genuine failure the person uploading has to resolve.
        if doc.needs_pass and not doc.authenticate(""):
            raise PdfExtractionError(
                "This PDF is password-protected. Remove the password and try again."
            )
        document.page_count = len(doc)
        for page_number, page in enumerate(doc, start=1):
            document.pages.append(extract_page(page_number, page))
    except PdfExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PdfExtractionError(
            "Could not read this file as a PDF ({}).".format(exc)
        ) from exc
    finally:
        doc.close()

    return document
