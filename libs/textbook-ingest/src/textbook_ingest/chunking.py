"""S8 -- group paragraphs into chunks worth embedding.

Three deliberate departures from the single-book version.

OVERLAP IS SMALL, AND THE FIRST MEASUREMENT OF IT WAS MISLEADING.
Rebuilding the MSCERT corpus at 105 and at 0 and checking the 39 gold answer
PHRASES: all 39 survive either way, so overlap looked like pure cost. Those
phrases are a few words each, and a short phrase rarely straddles a boundary.
The 31 gold QUOTES -- whole multi-sentence passages -- do straddle: at 0 the
shadow definition splits so that "If an opaque object comes in the way..." is
in one chunk and "...is called the 'shadow of the object'" in the next, and the
definition is in neither whole. 29 of 31 survive at 0, 30 of 31 at 105, for 10
extra chunks. Measure this against the QUOTES, never the phrases.

TABLES BECOME THEIR OWN CHUNKS.
Extraction flattens a table into a run of cell values. Merged into the prose
beside it, that produced chunks like the Class 6 planet table glued in front of
the Mercury definition -- half numbers with no column to attach to, competing
for a 600-character passage budget with the definition it was stuck to.

THE PAGE A CHUNK IS CITED ON IS ALWAYS THE PAGE IT CAME FROM.
The old flush() left `start_page` unset on one path and `Chunk` fell back to
`start_page or 1`, so two chunks -- including the Milky Way definition -- were
cited as page 1. Here the start page is set wherever the buffer gains its first
paragraph, so it cannot be None when a chunk closes.
"""

import re
from typing import List, Optional, Sequence

from .apparatus import (
    is_question_only,
    keep_on_exercise_page,
    page_is_exercise,
    strip_apparatus,
)
from .structure import clean_heading, is_section_heading, looks_like_table_row
from .types import BookProfile, Chunk

_MIN_CHUNK_CHARS = 40
# A run of this many consecutive table-shaped paragraphs is a table.
_MIN_TABLE_RUN = 2


def _tail_overlap(text: str, overlap_chars: int) -> str:
    """The last whole sentences of a chunk, to prepend to the next one."""
    if overlap_chars <= 0 or len(text) <= overlap_chars:
        return ""
    tail = text[-overlap_chars:]
    match = re.search(r"(?<=[.!?])\s+", tail)
    return tail[match.end():].strip() if match else tail.strip()


def _split_long_paragraph(para: str, chunk_chars: int) -> List[str]:
    """Split an over-long paragraph on sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", para)
    out: List[str] = []
    current: List[str] = []
    length = 0
    for sentence in sentences:
        if length + len(sentence) > chunk_chars and current:
            out.append(" ".join(current))
            current, length = [], 0
        current.append(sentence)
        length += len(sentence) + 1
    if current:
        out.append(" ".join(current))
    return out


def chunk_pages(
    pages: Sequence[str],
    *,
    chunk_chars: int = 700,
    overlap_chars: int = 0,
    filter_apparatus: bool = True,
    exercise_page_ratio: float = 0.40,
    profile: Optional[BookProfile] = None,
    page_numbers: Optional[Sequence[Optional[int]]] = None,
    sources: Optional[Sequence[str]] = None,
) -> List[Chunk]:
    """Group reflowed paragraphs into chunks, tracking heading and page range."""
    chunks: List[Chunk] = []
    buffer: List[str] = []
    buffer_len = 0
    heading = ""
    start_page: Optional[int] = None
    end_page = 1
    source = ""

    def cite(index: int) -> int:
        """The number to show a student: the printed page when it is known."""
        if page_numbers and index - 1 < len(page_numbers):
            printed = page_numbers[index - 1]
            if printed:
                return printed
        return index

    def add(paragraph: str, page_number: int) -> None:
        """Put a paragraph in the buffer, keeping the page range honest."""
        nonlocal buffer_len, start_page, end_page
        if start_page is None:
            start_page = page_number
        end_page = page_number
        buffer.append(paragraph)
        buffer_len += len(paragraph) + 2

    def flush(carry: str = "", kind: str = "prose") -> None:
        nonlocal buffer, buffer_len, start_page
        if not buffer:
            return
        body = "\n\n".join(buffer).strip()
        if body:
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    text=body,
                    heading=heading,
                    page_start=cite(start_page if start_page is not None else end_page),
                    page_end=cite(end_page),
                    source=source,
                    kind=kind,
                )
            )
        buffer = []
        buffer_len = 0
        start_page = None
        if carry:
            add(carry, end_page)

    for page_index, page in enumerate(pages, start=1):
        if sources and page_index - 1 < len(sources):
            source = sources[page_index - 1]
        if not page.strip():
            continue

        paragraphs = [p.strip() for p in page.split("\n\n") if p.strip()]
        if filter_apparatus:
            if page_is_exercise(paragraphs, exercise_page_ratio, profile):
                # Flushed first so the section before is not merged across the
                # gap, then filtered hard rather than deleted -- the exercise
                # shares its page with the chapter summary, which is worth
                # keeping.
                flush()
                paragraphs = keep_on_exercise_page(paragraphs, profile)
            else:
                paragraphs = strip_apparatus(paragraphs, profile)

        table_run: List[str] = []

        def close_table() -> None:
            nonlocal table_run
            if len(table_run) >= _MIN_TABLE_RUN:
                flush()
                for row in table_run:
                    add(row, page_index)
                flush(kind="table")
            elif table_run:
                for row in table_run:
                    add(row, page_index)
            table_run = []

        for index, para in enumerate(paragraphs):
            if is_section_heading(paragraphs, index, profile):
                label = clean_heading(para, profile) if filter_apparatus else para
                if label or not filter_apparatus:
                    # A heading opens a new topic, so close the chunk rather
                    # than letting two sections blur into one vector.
                    close_table()
                    flush()
                    heading = label
                    continue
                # Rejected as a heading: fall through to body text. Deleting the
                # book's words is the one mistake no later stage can undo.

            if looks_like_table_row(para):
                table_run.append(para)
                continue
            close_table()

            if len(para) > chunk_chars:
                # The only cut that is not on a semantic boundary, so the only
                # place overlap earns anything.
                flush()
                pieces = _split_long_paragraph(para, chunk_chars)
                for piece in pieces:
                    add(piece, page_index)
                    flush(carry=_tail_overlap(piece, overlap_chars))
                flush()
                continue

            if buffer_len + len(para) > chunk_chars:
                flush()
            add(para, page_index)

        close_table()

    flush()

    kept = [c for c in chunks if len(c.text.strip()) >= _MIN_CHUNK_CHARS]
    if filter_apparatus:
        kept = [c for c in kept if c.kind == "table" or not is_question_only(c.text)]
    for index, chunk in enumerate(kept):
        chunk.ordinal = index
    return kept
