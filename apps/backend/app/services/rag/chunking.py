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
from app.services.rag import pdf_text
from app.services.rag.quality import (
    clean_heading,
    is_question_only,
    keep_on_exercise_page,
    page_is_exercise,
    strip_apparatus,
)


@dataclass
class Chunk:
    ordinal: int
    text: str
    heading: str
    page_start: int
    page_end: int

    def embedding_text(
        self, grade: int, subject: str, breadcrumb: bool = True
    ) -> str:
        """What actually gets embedded: breadcrumb, then prose.

        Kept separate from `text` so the stored chunk stays clean -- the prompt
        gets the prose and a citation line, not this.

        The breadcrumb only helps when the heading really is the subject. In the
        index built before `clean_heading` existed it often was not: "28620C",
        "B", "3. Fill in the blanks with the appropriate" and "5. Go toward the
        left and then to the right" were all prepended to real prose, pulling
        the vector towards nothing or towards the exercise. Headings are now
        validated before they get here, so a junk one is "" and the breadcrumb
        falls back to "Class 6 > Science".

        `breadcrumb=False` (RAG_EMBED_BREADCRUMB=0) drops it entirely, so the
        two can be compared on a real corpus rather than argued about.
        """
        if not breadcrumb:
            return self.text
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
    chunk_chars: int,
    overlap_chars: int,
    drop_exercises: bool = True,
    exercise_page_ratio: float = 0.40,
) -> List[Chunk]:
    """Group paragraphs into chunks, tracking heading and page range.

    With `drop_exercises`, three filters from `rag.quality` run first: whole
    exercise pages are skipped, apparatus paragraphs are stripped from the pages
    that remain, and a heading is only kept if it names a topic. A chunk left
    with nothing but questions is dropped at the end.

    Measured on the Class 6 book: 16 of 132 pages are treated as exercises,
    14.8% of the text goes, and none of the 69 answer phrases in the two
    evaluation sets is lost from the corpus. See
    `scripts/eval/corpus_filter_report.py`.
    """
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
        paragraphs = [p.strip() for p in page.split("\n\n") if p.strip()]
        if drop_exercises:
            if page_is_exercise(paragraphs, exercise_page_ratio):
                # An end-of-chapter exercise page. Flushed first so the section
                # before it is not merged across the gap, then filtered hard
                # rather than deleted -- the exercise shares this page with
                # "What we have learnt", and that summary is worth keeping.
                flush(carry_overlap=False)
                paragraphs = keep_on_exercise_page(paragraphs)
            else:
                paragraphs = strip_apparatus(paragraphs)
        for index, para in enumerate(paragraphs):
            if pdf_text.is_section_heading(paragraphs, index):
                # "" for a line that names no topic, so the breadcrumb falls
                # back to "Class 6 > Science" instead of carrying "28620C" or
                # an activity step into every vector in the section.
                label = clean_heading(para) if drop_exercises else para
                if not label and drop_exercises:
                    # Rejected as a heading, but the words are still the book's.
                    # Before reflow read each line against the next it called a
                    # lot of ordinary prose a heading -- "The support at which the
                    # rod of a lever is" is how p.96 defines the fulcrum -- and
                    # consuming one as a heading that is then thrown away deletes
                    # it from the corpus outright. Reflow no longer does that, but
                    # anything clean_heading rejects still falls through to body
                    # text, because deleting the book's words is the one mistake
                    # no later stage can undo.
                    pass
                else:
                    # A heading opens a new topic, so close the current chunk
                    # rather than letting two sections blur into one vector.
                    # Flushed before `end_page` moves to this page, so the chunk
                    # being closed is cited on the page its text actually ends
                    # on -- not where the next section starts.
                    flush(carry_overlap=False)
                    heading = label
                    start_page = page_number
                    end_page = page_number
                    continue

            end_page = page_number
            if start_page is None:
                start_page = page_number

            # A single paragraph longer than the target is split on sentences;
            # this is the worked-example and long-definition case.
            if len(para) > chunk_chars:
                flush()
                for sentence_group in _split_long_paragraph(para, chunk_chars):
                    buffer.append(sentence_group)
                    buffer_len += len(sentence_group)
                    flush()
                continue

            if buffer_len + len(para) > chunk_chars:
                flush()
            buffer.append(para)
            buffer_len += len(para) + 2

    flush()

    kept = [c for c in chunks if len(c.text.strip()) >= 40]
    if drop_exercises:
        # A chunk that only asks. An activity prompt -- "To which part of plants
        # are butterflies and insects attracted ?" -- embeds beautifully against
        # a student's question and answers none of it. Applied after merging, so
        # a rhetorical question inside prose is safe: its chunk has plenty of
        # statements around it.
        kept = [c for c in kept if not is_question_only(c.text)]
    # Re-number: flush() appends in order but overlap carries can leave gaps.
    for index, chunk in enumerate(kept):
        chunk.ordinal = index
    return kept


def _split_long_paragraph(para: str, chunk_chars: int) -> List[str]:
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
