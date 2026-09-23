"""
The intermediate document model.

Every stage of the pipeline reads and writes these objects rather
than passing around ad-hoc dicts. Stages annotate in place: the
extractor fills geometry and text, the detector fills language and
encoding, the classifier fills content_type, and so on. `to_dict`
exists only at the edges, for the API response and for debugging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

BBox = tuple[float, float, float, float]

# Content types the classifier can assign to a block.
CONTENT_TYPES = (
    "heading",
    "paragraph",
    "list_item",
    "table",
    "caption",
    "exercise",
    "formula",
    "image",
    "other",
)


@dataclass
class Span:
    """A run of characters sharing one font and size."""

    text: str
    font: str
    size: float
    bbox: BBox
    bold: bool = False
    italic: bool = False


@dataclass
class Line:
    spans: list[Span] = field(default_factory=list)
    bbox: BBox = (0.0, 0.0, 0.0, 0.0)

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)

    @property
    def x_starts(self) -> list[float]:
        """Left edge of each span -- the signal for column alignment."""
        return [span.bbox[0] for span in self.spans]


@dataclass
class Block:
    """
    One layout block: a paragraph, a heading, a table, an image.

    `text` is what came out of the PDF. `normalized_text` is what
    survives detection, legacy conversion and normalization, and is
    the only text that reaches chunking.
    """

    index: int
    kind: str                       # "text" | "image"
    bbox: BBox
    lines: list[Line] = field(default_factory=list)
    text: str = ""

    # Filled by layout.py
    column: int = 0
    order: int = 0

    # Filled by detect.py / legacy conversion
    normalized_text: str = ""
    language: str = "unknown"
    script: str = "unknown"
    encoding: str = "unknown"
    converted_from: str | None = None
    conversion_coverage: float | None = None

    # Filled by classify.py
    content_type: str = "other"
    content_confidence: float = 0.0
    classification_evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def fonts(self) -> list[str]:
        return sorted({span.font for line in self.lines for span in line.spans})

    @property
    def max_size(self) -> float:
        sizes = [span.size for line in self.lines for span in line.spans]
        return max(sizes) if sizes else 0.0

    @property
    def is_bold(self) -> bool:
        spans = [span for line in self.lines for span in line.spans if span.text.strip()]
        if not spans:
            return False
        return all(span.bold for span in spans)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "bbox": self.bbox,
            "column": self.column,
            "order": self.order,
            "text": self.text,
            "normalized_text": self.normalized_text,
            "content_type": self.content_type,
            "content_confidence": self.content_confidence,
            "language": self.language,
            "script": self.script,
            "encoding": self.encoding,
            "converted_from": self.converted_from,
            "conversion_coverage": self.conversion_coverage,
            "fonts": self.fonts,
        }


@dataclass
class Page:
    number: int
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)

    # Filled by layout.py
    column_count: int = 1

    # Filled by detect.py
    stats: dict[str, Any] = field(default_factory=dict)
    detection: dict[str, Any] = field(default_factory=dict)

    @property
    def text_blocks(self) -> list[Block]:
        return [block for block in self.blocks if block.kind == "text"]

    @property
    def text(self) -> str:
        """Raw extracted text, in reading order."""
        return "\n".join(
            block.text for block in sorted(self.text_blocks, key=lambda b: b.order)
            if block.text.strip()
        )

    @property
    def normalized_text(self) -> str:
        return "\n".join(
            block.normalized_text
            for block in sorted(self.text_blocks, key=lambda b: b.order)
            if block.normalized_text.strip()
        )

    @property
    def fonts(self) -> list[str]:
        return sorted({font for block in self.blocks for font in block.fonts})

    @property
    def font_usage(self) -> dict[str, int]:
        usage: dict[str, int] = {}
        for block in self.blocks:
            for line in block.lines:
                for span in line.spans:
                    usage[span.font] = usage.get(span.font, 0) + len(span.text)
        return dict(sorted(usage.items(), key=lambda item: item[1], reverse=True))

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.number,
            "width": self.width,
            "height": self.height,
            "column_count": self.column_count,
            "stats": self.stats,
            "detection": self.detection,
            "fonts": self.fonts,
            "font_usage": self.font_usage,
            "blocks": [block.to_dict() for block in self.blocks],
        }


@dataclass
class Document:
    document_id: str
    file_name: str
    source_path: str = ""
    sha256: str = ""
    page_count: int = 0
    pages: list[Page] = field(default_factory=list)

    # Caller-supplied bibliographic metadata (subject, class, chapter...).
    meta: dict[str, Any] = field(default_factory=dict)

    # Filled by detect.py
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "file_name": self.file_name,
            "sha256": self.sha256,
            "page_count": self.page_count,
            "meta": self.meta,
            "summary": self.summary,
            "pages": [page.to_dict() for page in self.pages],
        }


@dataclass
class Chunk:
    """A retrieval unit, ready to embed."""

    chunk_id: str
    document_id: str
    text: str

    page: int = 0
    page_end: int = 0
    content_type: str = "paragraph"
    language: str = "unknown"
    script: str = "unknown"
    section: str = ""
    chapter: str = ""
    parent_id: str | None = None
    token_estimate: int = 0
    text_hash: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    # Filled by validate.py
    valid: bool = True
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "text": self.text,
            "page": self.page,
            "page_end": self.page_end,
            "content_type": self.content_type,
            "language": self.language,
            "script": self.script,
            "section": self.section,
            "chapter": self.chapter,
            "parent_id": self.parent_id,
            "token_estimate": self.token_estimate,
            "text_hash": self.text_hash,
            "meta": self.meta,
            "valid": self.valid,
            "issues": self.issues,
        }
