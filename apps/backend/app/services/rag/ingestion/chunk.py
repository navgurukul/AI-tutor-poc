"""
Stage 7 -- adaptive chunking.

Chunk boundaries decide what the tutor can answer. A boundary in
the middle of an explanation means neither half retrieves; a chunk
spanning two unrelated sections means the wrong half gets quoted.

So the rules differ by content type:

  prose      section -> paragraph -> sentence, sized to
             `rag_chunk_target_tokens`, with one sentence of overlap
             so a fact split across a boundary still appears whole
             somewhere.
  table      never merged with prose, split by rows with the header
             row repeated, because a row without its header is
             meaningless.
  exercise   the question and everything under it stay together up
             to the next heading.
  formula    attached to the prose around it; a bare equation has
             nothing for an embedding to grip.
  caption    kept with its figure reference rather than dissolved
             into the surrounding text.

Headings are never chunks on their own. They travel as the
`section` field on every chunk beneath them, which is what lets the
retriever tell "Water cycle: evaporation" from "Rock cycle:
evaporation".
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.config import settings

from .model import Block, Chunk, Document, Page
from .scripts import estimate_tokens

# Sizing comes from config, not from constants here, because these numbers
# have to agree with `rag_passage_token_cap` -- the number of tokens a
# retrieved passage is allowed to contribute to the prompt. The upstream
# values (260 target / 420 max) were sized for a retriever that sends four
# passages plus neighbour windows; this one sends one passage, trimmed.
#
# When the target exceeds the cap, `retrieval.trim_passage` cuts the chunk to
# its leading sentences and the rest of it can never reach the model. Measured
# on the Class X Geography library before this port: median chunk 344 tokens
# against a 70-token cap, so 83% of the corpus was unreachable and the passage
# that answered a question routinely arrived without the sentence that
# answered it. See EXP-019.
def _target_tokens() -> int:
    return settings.rag_chunk_target_tokens


def _max_tokens() -> int:
    return settings.rag_chunk_max_tokens


# Read once at import for the module-level constants that `validate.py` and
# the tests refer to. The functions above are what the builder calls, so a
# settings override at runtime still takes effect.
TARGET_TOKENS = settings.rag_chunk_target_tokens
MAX_TOKENS = settings.rag_chunk_max_tokens
MIN_TOKENS = settings.rag_chunk_min_tokens
OVERLAP_SENTENCES = 1

# Content types that always stand alone.
STANDALONE = {"table", "exercise"}

# Content types that carry no retrievable content by themselves.
#
# `furniture` is the running head, the folio and the reprint watermark, marked
# by the stage of that name. It must be skipped BEFORE the exercise grouping
# below, or a page number between two exercise blocks would break the run.
SKIP = {"image", "furniture"}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।॥])[ \t]+|\n+")

# Periods that do not end a sentence.
_ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "prof", "fig", "eg", "ie", "etc", "vs",
    "no", "vol", "ch", "sec", "pp", "st", "approx", "ex",
    # Science textbooks cross-reference constantly.
    "eq", "eqn", "ref", "art", "col", "sl",
}

_ABBREV_TAIL = re.compile(r"(?:^|\s)([A-Za-z]{1,6})\.$")


def _is_abbreviation_end(fragment: str) -> bool:
    match = _ABBREV_TAIL.search(fragment.strip())
    if not match:
        return False
    word = match.group(1).lower()
    # A single letter is only PROVISIONALLY an abbreviation -- "J. Smith" is an
    # initial, but "charge Q." is a sentence ending in a symbol. Which one it
    # is cannot be told from the fragment alone, so the caller decides by
    # looking at what follows. See `_continues_previous`.
    return word in _ABBREVIATIONS or len(word) == 1


# What follows an abbreviation decides whether it really ended the sentence.
#
# The physics books made this unavoidable. Their prose names quantities with
# single capitals -- "...the repulsive force on it due to the charge Q. With
# reference to..." -- and treating every single letter before a period as an
# initial meant those sentences NEVER split. The accumulator then closed a
# chunk wherever the token target happened to fall, mid-sentence:
#
#     "...from a point R to a point P against the repulsive force on it due
#      to the charge Q. With reference"
#
# 18-22% of paragraph chunks in leph101/leph102 ended like that.
#
# A capital letter starting the next fragment means a new sentence began, so
# the period was terminal. Anything else -- a lowercase word ("e.g. the"), a
# digit ("Fig. 2"), a bracket ("Eq. (2.2)") -- is a continuation.
_STARTS_A_SENTENCE = re.compile(r"^[A-Zऀ-ॿ]")


def _continues_previous(previous: str, piece: str) -> bool:
    if not _is_abbreviation_end(previous):
        return False
    tail = _ABBREV_TAIL.search(previous.strip())
    word = tail.group(1).lower() if tail else ""
    if word in _ABBREVIATIONS:
        # A known abbreviation is one whatever follows it: "etc. The next..."
        # is still one sentence by this rule, which is the safer error -- it
        # joins two sentences rather than cutting one in half.
        return True
    return not _STARTS_A_SENTENCE.match(piece.strip())


def split_sentences(text: str) -> list[str]:
    """
    Split into sentences, handling the Devanagari danda alongside
    Latin punctuation and rejoining common abbreviations.
    """
    if not text.strip():
        return []

    pieces = [piece.strip() for piece in _SENTENCE_SPLIT.split(text) if piece and piece.strip()]
    if not pieces:
        return []

    merged = [pieces[0]]
    for piece in pieces[1:]:
        if _continues_previous(merged[-1], piece):
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)

    return merged


# A block whose tokens are mostly single characters is positioned
# glyphs rather than words. Mirrors the validator's threshold, so a
# fragment is caught before it contaminates a chunk rather than
# after, when the whole chunk has to be thrown away.
MAX_SINGLE_CHAR_TOKENS = 0.25

# ...unless real words are present. An equation quoted inside a
# sentence ("E = mc^2 where c is the speed of light") is dense in
# single characters for a good reason: operators and variable names
# are single characters. What separates it from scrambled glyph
# soup is that words survive alongside them.
MIN_REAL_WORDS = 4

_REAL_WORD = re.compile(r"[A-Za-zऀ-ॿ]{3,}")


def is_readable(text: str) -> bool:
    """True when the text reads as words rather than loose glyphs."""
    tokens = text.split()
    if len(tokens) < 4:
        return True

    singles = sum(1 for token in tokens if len(token) == 1)
    if singles / len(tokens) <= MAX_SINGLE_CHAR_TOKENS:
        return True

    return len(_REAL_WORD.findall(text)) >= MIN_REAL_WORDS


def chunk_id_for(document_id: str, page: int, index: int, text: str) -> str:
    """
    A chunk id that is stable across re-ingests of the same file.

    Includes the text hash so that an edited page produces new ids
    rather than silently overwriting a chunk whose content moved.
    """
    digest = hashlib.sha1(
        f"{document_id}|{page}|{index}|{text}".encode("utf-8")
    ).hexdigest()
    return f"{document_id}:{page:04d}:{index:03d}:{digest[:10]}"


def text_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


@dataclass
class _Accumulator:
    """Prose collected so far, waiting to reach the target size."""

    sentences: list[str] = field(default_factory=list)
    page_start: int = 0
    page_end: int = 0
    language: str = "unknown"
    script: str = "unknown"
    content_type: str = "paragraph"

    @property
    def text(self) -> str:
        return " ".join(self.sentences).strip()

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)

    def is_empty(self) -> bool:
        return not self.sentences


class _Builder:
    """Assembles chunks while walking the document in reading order."""

    def __init__(self, document: Document):
        self.document = document
        self.chunks: list[Chunk] = []
        self.accumulator = _Accumulator()
        self.section = ""
        self.chapter = str(document.meta.get("chapter", "") or "")
        self.section_parent: str | None = None
        self.counter = 0

    # -- emitting ----------------------------------------------------

    def _emit(
        self,
        text: str,
        page: int,
        page_end: int,
        content_type: str,
        language: str,
        script: str,
    ) -> Chunk | None:
        text = text.strip()
        if not text:
            return None

        index = self.counter
        self.counter += 1

        chunk = Chunk(
            chunk_id=chunk_id_for(self.document.document_id, page, index, text),
            document_id=self.document.document_id,
            text=text,
            page=page,
            page_end=max(page, page_end),
            content_type=content_type,
            language=language,
            script=script,
            section=self.section,
            chapter=self.chapter,
            token_estimate=estimate_tokens(text),
            text_hash=text_hash(text),
            meta=dict(self.document.meta),
        )

        # The first chunk of a section parents the rest of it, giving
        # retrieval a handle on "the section this came from".
        if self.section_parent is None:
            self.section_parent = chunk.chunk_id
        else:
            chunk.parent_id = self.section_parent

        self.chunks.append(chunk)
        return chunk

    def flush(self) -> None:
        """Emit whatever prose is buffered."""
        if self.accumulator.is_empty():
            return

        accumulator = self.accumulator
        self._emit(
            accumulator.text,
            accumulator.page_start,
            accumulator.page_end,
            accumulator.content_type,
            accumulator.language,
            accumulator.script,
        )
        self.accumulator = _Accumulator()

    def _begin(self, block: Block, page: Page) -> None:
        """Open a fresh prose buffer positioned at this block."""
        self.accumulator = _Accumulator(
            page_start=page.number,
            page_end=page.number,
            language=block.language,
            script=block.script,
        )

    # -- consuming ---------------------------------------------------

    def add_prose(self, block: Block, page: Page) -> None:
        sentences = split_sentences(block.normalized_text)
        if not sentences:
            return

        # A language switch mid-buffer means two different texts got
        # adjacent on the page. Never embed them as one chunk.
        if (
            not self.accumulator.is_empty()
            and self.accumulator.language != "unknown"
            and block.language != "unknown"
            and self.accumulator.language != block.language
        ):
            self.flush()

        if self.accumulator.is_empty():
            self._begin(block, page)

        self.accumulator.page_end = page.number

        for sentence in sentences:
            sentence_tokens = estimate_tokens(sentence)

            # A single sentence longer than the ceiling is split on
            # whitespace: rare, but it must not be dropped.
            if sentence_tokens > _max_tokens():
                self.flush()
                for part in self._split_oversize(sentence):
                    self._emit(part, page.number, page.number, "paragraph",
                               block.language, block.script)
                self._begin(block, page)
                continue

            if (
                self.accumulator.sentences
                and self.accumulator.tokens + sentence_tokens > _target_tokens()
            ):
                carried = self._overlap_tail()
                self.flush()
                self._begin(block, page)
                self.accumulator.sentences.extend(carried)

            self.accumulator.sentences.append(sentence)

    def _overlap_tail(self) -> list[str]:
        """
        The trailing sentences to repeat in the next chunk.

        Dropped if the tail is itself large: carrying half a chunk
        forward duplicates content without buying context.
        """
        budget = settings.rag_chunk_overlap_max_tokens
        if not OVERLAP_SENTENCES or budget <= 0:
            return []

        tail = self.accumulator.sentences[-OVERLAP_SENTENCES:]
        # An absolute token budget, not a fraction of the chunk. The old guard
        # was `target // 2`, which at a 70-token target let 35 tokens through
        # and made 44% of the library a repeat of itself -- see
        # `rag_chunk_overlap_max_tokens` for what that costs at retrieval time.
        if estimate_tokens(" ".join(tail)) > budget:
            return []

        return list(tail)

    def _split_oversize(self, sentence: str) -> list[str]:
        words = sentence.split()
        parts: list[str] = []
        current: list[str] = []

        for word in words:
            current.append(word)
            if estimate_tokens(" ".join(current)) >= _target_tokens():
                parts.append(" ".join(current))
                current = []

        if current:
            parts.append(" ".join(current))

        return parts

    def add_table(self, block: Block, page: Page) -> None:
        self.flush()

        lines = [line for line in block.normalized_text.split("\n") if line.strip()]
        if not lines:
            return

        if estimate_tokens(block.normalized_text) <= _max_tokens():
            self._emit(block.normalized_text, page.number, page.number, "table",
                       block.language, block.script)
            return

        # Repeat the first row in each part: a data row without its
        # header cannot be interpreted by the model or the student.
        header, rows = lines[0], lines[1:]
        current = [header]

        for row in rows:
            candidate = current + [row]
            if estimate_tokens("\n".join(candidate)) > _max_tokens() and len(current) > 1:
                self._emit("\n".join(current), page.number, page.number, "table",
                           block.language, block.script)
                current = [header, row]
            else:
                current = candidate

        if len(current) > 1:
            self._emit("\n".join(current), page.number, page.number, "table",
                       block.language, block.script)

    def add_exercise(self, blocks: list[tuple[Page, Block]]) -> None:
        self.flush()
        if not blocks:
            return

        text = "\n".join(block.normalized_text for _, block in blocks if block.normalized_text.strip())
        if not text.strip():
            return

        first_page = blocks[0][0].number
        last_page = blocks[-1][0].number
        language = blocks[0][1].language
        script = blocks[0][1].script

        if estimate_tokens(text) <= _max_tokens():
            self._emit(text, first_page, last_page, "exercise", language, script)
            return

        # Too long to hold together: split between questions rather
        # than mid-question.
        current: list[str] = []
        for _, block in blocks:
            candidate = current + [block.normalized_text]
            if estimate_tokens("\n".join(candidate)) > _max_tokens() and current:
                self._emit("\n".join(current), first_page, last_page, "exercise",
                           language, script)
                current = [block.normalized_text]
            else:
                current = candidate

        if current:
            self._emit("\n".join(current), first_page, last_page, "exercise",
                       language, script)

    def start_section(self, block: Block) -> None:
        self.flush()
        self.section = block.normalized_text.strip()
        self.section_parent = None


def _ordered_blocks(document: Document) -> list[tuple[Page, Block]]:
    units: list[tuple[Page, Block]] = []
    for page in document.pages:
        for block in sorted(page.blocks, key=lambda b: b.order):
            units.append((page, block))
    return units


def chunk_document(document: Document) -> list[Chunk]:
    """Turn a normalized, classified document into retrieval chunks."""
    builder = _Builder(document)
    units = _ordered_blocks(document)

    index = 0
    while index < len(units):
        page, block = units[index]

        if block.content_type in SKIP or not block.normalized_text.strip():
            index += 1
            continue

        if block.content_type == "heading":
            builder.start_section(block)
            index += 1
            continue

        if block.content_type == "table":
            builder.add_table(block, page)
            index += 1
            continue

        if block.content_type == "exercise":
            # Absorb the whole exercise run: the question block plus
            # the list items and prose under it.
            group = [(page, block)]
            index += 1
            while index < len(units):
                next_page, next_block = units[index]
                if next_block.content_type in {"heading", "table"}:
                    break
                if next_block.content_type == "exercise":
                    break
                # Furniture and images are stepped OVER, not absorbed and not
                # treated as the end of the run. Without this, the running
                # head and folio printed between two pages of an exercise were
                # pulled into the question -- an exercise chunk reading
                # "(a) Punjab ... (d) Jharkhand / 1 / Contemporary India-2  2".
                if next_block.content_type in SKIP:
                    index += 1
                    continue
                if not next_block.normalized_text.strip():
                    index += 1
                    continue
                group.append((next_page, next_block))
                index += 1
            builder.add_exercise(group)
            continue

        if block.content_type == "formula":
            # A formula is glued onto the prose buffer so it keeps
            # the sentence that explains it -- but only if it came
            # out of the PDF as readable text.
            #
            # A displayed equation is positioned glyphs, not
            # structure: a fraction's numerator and denominator are
            # separate runs, and linearising them by position gives
            # "0 ( ) 4 Q V r r ε = π" for Q/4πε₀r. Merged into the
            # buffer that scrambling fails the fragmentation check
            # and takes the surrounding explanation down with it.
            # Measured on one physics chapter: 19% of the text
            # rejected, and 22 of the 26 rejected chunks held prose
            # that was fine on its own.
            #
            # So an unreadable formula is dropped and its
            # explanation kept. Half a derivation beats none.
            if is_readable(block.normalized_text):
                builder.add_prose(block, page)
            index += 1
            continue

        builder.add_prose(block, page)
        index += 1

    builder.flush()

    return [chunk for chunk in builder.chunks if chunk.token_estimate >= settings.rag_chunk_min_tokens]


def embedding_text(chunk: Chunk) -> str:
    """
    The string actually sent to the embedder.

    Chunk text stays clean for display and for the answer prompt;
    the heading path is prepended only here, so that a chunk reading
    "It evaporates and rises" still carries "Water cycle" into
    vector space.
    """
    prefix_parts = [part for part in (chunk.chapter, chunk.section) if part]
    subject = chunk.meta.get("subject")
    if subject:
        prefix_parts.insert(0, str(subject))

    if not prefix_parts:
        return chunk.text

    return f"{' › '.join(prefix_parts)}\n{chunk.text}"
