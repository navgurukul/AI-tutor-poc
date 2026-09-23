"""
Stage 5 -- text normalization.

Turns extracted lines back into prose: joins soft-wrapped lines,
repairs words split across a line break, and standardises Unicode
and whitespace.

Deliberately conservative about Indic text. ZWJ and ZWNJ are real
letters' worth of meaning in Devanagari, so they survive, and
hyphen-joining is applied only to Latin words, where the convention
is unambiguous.
"""

from __future__ import annotations

import re
import unicodedata

from app.services.rag import devanagari

from .model import Block, Document, Page
from .scripts import DEV_DANDA, DEV_DOUBLE_DANDA
from .symbolfont import decode as decode_symbol_font

# Invisible characters that carry no meaning and break matching.
# U+200C/U+200D are excluded: they are meaningful in Devanagari.
_ZERO_WIDTH = re.compile("[​‎‏﻿­]")

# A Latin word broken across a line by a hyphen.
_SOFT_HYPHEN_BREAK = re.compile(r"([A-Za-z])[-‐‑]\n([a-z])")

# Line endings that really do end a sentence or heading.
_HARD_LINE_END = re.compile(
    f"[.!?:;{DEV_DANDA}{DEV_DOUBLE_DANDA}•…]\\s*$"
)

_MULTI_SPACE = re.compile(r"[ \t ]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCT = re.compile(f"\\s+([,.;:!?{DEV_DANDA}])")


def join_soft_wraps(text: str) -> str:
    """
    Rejoin lines that were wrapped by the layout rather than ended
    by the author.

    A line that stops mid-sentence is a wrap; one that ends in
    terminal punctuation is kept as its own line.
    """
    text = _SOFT_HYPHEN_BREAK.sub(r"\1\2", text)

    lines = text.split("\n")
    if len(lines) < 2:
        return text

    out = [lines[0]]

    for line in lines[1:]:
        previous = out[-1]

        if previous.strip() and not _HARD_LINE_END.search(previous):
            separator = "" if previous.endswith(("-", "‐")) else " "
            out[-1] = previous.rstrip() + separator + line.lstrip()
        else:
            out.append(line)

    return "\n".join(out)


def clean(text: str) -> str:
    """Standardise Unicode form and whitespace."""
    if not text:
        return ""

    # Maths set in the Symbol font arrives in the private-use area:
    # U+F0B5 where the page shows ∝. Decoded before anything else,
    # so the rest of normalization sees real characters.
    text = decode_symbol_font(text)

    text = unicodedata.normalize("NFC", text)

    # Devanagari the font's own character map got wrong: doubled matras, and
    # the फ family (कार्टोग्राप़्ाफी -> कार्टोग्राफी, उफर्जा -> ऊर्जा). After NFC,
    # because the patterns are written against composed text; before anything
    # that splits words, because each one spans several characters.
    text = devanagari.repair(text)

    text = _ZERO_WIDTH.sub("", text)
    text = text.replace(" ", " ")

    # Strip control characters that survive extraction, keeping
    # newline and tab.
    text = "".join(
        char
        for char in text
        if char in "\n\t" or unicodedata.category(char) != "Cc"
    )

    text = _MULTI_SPACE.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MULTI_NEWLINE.sub("\n\n", text)

    return text.strip()


def normalize_block(block: Block) -> None:
    """
    Normalize one block in place.

    Tables keep their line structure: the line breaks *are* the row
    boundaries, and joining them would destroy the only structure a
    table has once it leaves the PDF.
    """
    source = block.normalized_text or block.text

    if block.content_type == "table":
        block.normalized_text = clean(source)
    else:
        block.normalized_text = clean(join_soft_wraps(source))


def normalize_page(page: Page) -> None:
    for block in page.text_blocks:
        normalize_block(block)


def normalize_document(document: Document) -> None:
    for page in document.pages:
        normalize_page(page)
