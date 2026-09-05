"""Split cleaned textbook text into chunks worth embedding.

Two things make a chunk retrievable. It has to be about one thing, which means
splitting on paragraph boundaries rather than a fixed character count that cuts
sentences in half. And it has to say what it is about, because a paragraph
lifted out of a chapter often never repeats the noun it is explaining -- three
paragraphs into "Tissues", the text says "they" and "these cells", and embedded
on its own that paragraph matches nothing a student would type.

The fix for the second problem is the breadcrumb: every chunk is embedded with
"Class 9 > Science > Tissues >" in front of it, so the chapter's vocabulary is
part of the vector even when the prose has moved on. The breadcrumb is stripped
before the text is shown to the model, which only needs the prose.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

# Heading detection lives in pdf_text because reflow has to apply it first --
# a heading only reaches this module as its own paragraph because that pass
# already recognised it. Shared rather than duplicated so the two agree.
from app.services.rag.pdf_text import looks_like_heading


@dataclass
class Chunk:
    ordinal: int
    text: str
    heading: str
    page_start: int
    page_end: int

    def embedding_text(self, grade: int, subject: str) -> str:
        """What actually gets embedded: breadcrumb, then prose.

        Kept separate from `text` so the stored chunk stays clean -- the prompt
        gets the prose and a citation line, not this.
        """
        crumbs = ["Class {}".format(grade), subject]
        if self.heading:
            crumbs.append(self.heading)
        return "{}\n\n{}".format(" > ".join(crumbs), self.text)


def _tail_overlap(text: str, overlap_chars: int) -> str:
    """The last whole sentences of a chunk, to prepend to the next one.

    Overlap is taken at a sentence boundary rather than a character count so
    the carried-over text still reads as language; a half sentence at the head
    of a chunk pollutes its embedding for no retrieval benefit.
    """
    if overlap_chars <= 0 or len(text) <= overlap_chars:
        return ""
    tail = text[-overlap_chars:]
    match = re.search(r"(?<=[.!?])\s+", tail)
    return tail[match.end():].strip() if match else tail.strip()


def chunk_pages(
    pages: Sequence[str],
    target_chars: int,
    overlap_chars: int,
    max_chars: Optional[int] = None,
    min_chars: int = 40,
) -> List[Chunk]:
    """Group paragraphs into chunks, tracking heading and page range.

    Three bounds, not one. Packing aims at `target_chars`; only a paragraph
    that on its own exceeds `max_chars` is split on sentences. The gap between
    them is deliberate -- a section that runs to 1,400 characters is better
    kept whole than cut at 1,201, because the cut lands mid-explanation and
    both halves embed worse than the whole did.
    """
    max_chars = max_chars or int(target_chars * 1.65)
    chunks: List[Chunk] = []
    buffer: List[str] = []
    buffer_len = 0
    heading = ""
    start_page: Optional[int] = None
    end_page = 1

    def flush(carry_overlap: bool = True) -> None:
        """Close the current chunk.

        `carry_overlap=False` at a heading: overlap exists so a definition split
        across a boundary survives in both neighbours, but a heading *is* the
        boundary between topics. Carrying the previous section's tail into the
        next one both mixes two subjects in one vector and labels that text with
        the wrong heading.
        """
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
                    page_start=start_page or 1,
                    page_end=end_page,
                )
            )
        carry = _tail_overlap(body, overlap_chars) if carry_overlap else ""
        buffer = [carry] if carry else []
        buffer_len = len(carry)
        start_page = end_page if carry else None

    for page_number, page in enumerate(pages, start=1):
        if not page.strip():
            continue
        for para in page.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            if looks_like_heading(para):
                # A heading opens a new topic, so close the current chunk
                # rather than letting two sections blur into one vector.
                # Flushed before `end_page` moves to this page, so the chunk
                # being closed is cited on the page its text actually ends on
                # -- not on the page where the next section starts.
                flush(carry_overlap=False)
                heading = para
                start_page = page_number
                end_page = page_number
                continue

            end_page = page_number
            if start_page is None:
                start_page = page_number

            # Only a paragraph past the hard maximum is split on sentences;
            # this is the worked-example and long-definition case. Between
            # target and max it is left whole.
            if len(para) > max_chars:
                flush()
                for sentence_group in _split_long_paragraph(para, max_chars):
                    buffer.append(sentence_group)
                    buffer_len += len(sentence_group)
                    flush()
                continue

            # Adding this paragraph would pass the target. Close the chunk
            # first -- unless doing so would leave the paragraph to start a
            # chunk that then exceeds max on its own, which the branch above
            # has already ruled out.
            if buffer_len and buffer_len + len(para) > target_chars:
                flush()
            buffer.append(para)
            buffer_len += len(para) + 2

    flush()
    # Re-number: flush() appends in order but overlap carries can leave gaps.
    for index, chunk in enumerate(chunks):
        chunk.ordinal = index
    return [c for c in chunks if len(c.text.strip()) >= min_chars]


def _split_long_paragraph(para: str, max_chars: int) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", para)
    out: List[str] = []
    current: List[str] = []
    length = 0
    for sentence in sentences:
        if length + len(sentence) > max_chars and current:
            out.append(" ".join(current))
            current, length = [], 0
        current.append(sentence)
        length += len(sentence) + 1
    if current:
        out.append(" ".join(current))
    return out
