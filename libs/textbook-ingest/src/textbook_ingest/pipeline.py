"""The whole pipeline, and the one function most callers need.

    from textbook_ingest import ingest, Source

    result = ingest([Source("book.pdf", data)])
    for chunk in result.chunks:
        index(chunk.text, chunk.page_start)

Order matters and is not arbitrary:

    extract -> assess -> vocabulary -> repair -> PROFILE -> strip -> reflow -> chunk

The profile has to be built AFTER repair, because it learns from the text: a
running header that reads "SCIENCE58" on one page and "S CIENCE58" on another
(the intra-word split defect) would otherwise produce two templates instead of
one. And it has to be built BEFORE strip and reflow, because both of those are
driven by what it learned.

The vocabulary is built before repair for the same reason in reverse -- repair
needs to know which words this book uses, and it has to get that from the
unrepaired text, which is the only text there is at that point. Words broken by
a stray space simply do not appear in it, which is exactly the signal repair
relies on.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence

from . import fidelity as _fidelity
from . import matter as _matter
from . import profile as _profile
from . import repair as _repair
from . import reflow as _reflow
from . import strip as _strip
from .chunking import chunk_pages
from .errors import UnusableBook
from .extract import extract, sources_from_paths
from .types import BookProfile, IngestResult, Source, Warning_

logger = logging.getLogger(__name__)


@dataclass
class IngestOptions:
    """Everything a caller might want to change, with measured defaults."""

    chunk_chars: int = 700
    # Small but not zero. Short answer phrases never depend on overlap, but
    # whole multi-sentence passages do: at 0 the Class 6 shadow definition
    # breaks across two chunks and is in neither whole. See chunking.py.
    overlap_chars: int = 105
    filter_apparatus: bool = True
    exercise_page_ratio: float = 0.40
    # Text repair is on by default; it is what makes NCERT Class 9 Science
    # (16.1 broken words per 1,000) comparable to the MSCERT book (1.0).
    repair_text: bool = True
    # Refuse a book whose text cannot be read. Turning this off ingests it
    # anyway, which is what the old pipeline did to Class 1 Math-Magic.
    enforce_fidelity: bool = True
    # Drop the cover, credits, contents and glossary. Measured at 9% of the
    # shipped MSCERT corpus, none of it able to answer a question. Off for a
    # document that IS reference material rather than a textbook.
    drop_matter: bool = True
    # A profile supplied by hand, for a book the detector gets wrong.
    profile: Optional[BookProfile] = None


def _page_numbers(pages: Sequence[str], furniture) -> List[Optional[int]]:
    """The printed page number of each page, where one can be found.

    Worth the effort because it is what a citation shows a student. NCERT hides
    the number inside the running header ("SCIENCE58"), so the digits removed
    when a line matches a furniture template are exactly the page number.
    """
    import re

    numbers: List[Optional[int]] = []
    for page in pages:
        found: Optional[int] = None
        lines = [l.strip() for l in page.splitlines() if l.strip()]
        for line in lines[:3] + lines[-3:]:
            if _strip._PAGE_NUMBER.match(line):
                digits = re.findall(r"\d{1,4}", line)
                if digits:
                    found = int(digits[0])
                    break
            if _profile.template(line) in furniture:
                digits = re.findall(r"\d{1,4}", line)
                if digits:
                    found = int(digits[0])
                    break
        numbers.append(found)
    return _interpolate(numbers)


def _interpolate(numbers: List[Optional[int]]) -> List[Optional[int]]:
    """Fill in pages whose number did not survive extraction.

    A chapter's opening page usually carries no running header -- the title
    occupies it -- so its number is missing exactly where a citation is most
    likely to be wanted. Neighbouring pages are numbered consecutively, so the
    gap can be closed from either side. Only immediate neighbours are used: a
    guess two pages from any evidence is not worth showing a student.
    """
    filled = list(numbers)
    for i, value in enumerate(filled):
        if value is not None:
            continue
        before = filled[i - 1] if i > 0 else None
        after = numbers[i + 1] if i + 1 < len(numbers) else None
        if before is not None and (after is None or after == before + 2):
            filled[i] = before + 1
        elif after is not None and after > 1:
            filled[i] = after - 1
    return filled


def ingest(sources: Sequence[Source], options: Optional[IngestOptions] = None) -> IngestResult:
    """PDF bytes in, chunks out, with every loss reported."""
    options = options or IngestOptions()
    result = IngestResult()

    # --- S0 extract, one source at a time ---------------------------------
    pages, warnings, skipped = extract(sources)
    result.warnings.extend(warnings)
    result.skipped = skipped
    if not pages:
        raise UnusableBook(
            "No pages could be read from this book.",
            hint="Check the files are PDFs and are not empty.",
            code="no_pages",
        )

    raw = [p.raw for p in pages]

    # --- S1 is this text usable at all? ------------------------------------
    report = _fidelity.assess(raw)
    result.stats["fidelity"] = report.stats
    for reason in report.reasons:
        result.warnings.append(Warning_("fidelity", reason))
    if report.verdict == "reject" and options.enforce_fidelity:
        raise UnusableBook(
            "; ".join(report.reasons) or "The text in this PDF cannot be read.",
            hint=report.hint,
            code=report.code,
        )

    # --- S2 repair ---------------------------------------------------------
    normalised = [
        _repair.normalise_characters(page, report.space_substitute) for page in raw
    ]
    vocabulary = _fidelity.summarise_vocabulary(normalised)
    if options.repair_text:
        repaired = [
            _repair.repair_page(page, vocabulary, report.space_substitute) for page in raw
        ]
    else:
        repaired = normalised

    # --- S3 learn this book ------------------------------------------------
    book = options.profile or _profile.build_profile(
        repaired, vocabulary=vocabulary, space_substitute=report.space_substitute
    )
    result.profile = book
    result.stats["profile"] = book.as_dict()

    # --- S4 strip the furniture -------------------------------------------
    numbers = _page_numbers(repaired, book.furniture)
    stripped = _strip.strip_pages(repaired, book.furniture)

    # --- S5 reflow ---------------------------------------------------------
    reflowed = _reflow.reflow_pages(stripped, book)
    for page, text, number in zip(pages, reflowed, numbers):
        page.text = text
        page.number = number
        page.paragraphs = [p for p in text.split("\n\n") if p.strip()]
    result.pages = pages

    # --- S6 drop what is not the book -------------------------------------
    if options.drop_matter:
        start, end, matter_warnings = _matter.find_body(reflowed, numbers)
        result.warnings.extend(matter_warnings)
    else:
        start, end = 0, len(reflowed)
    body = reflowed[start:end]
    body_numbers = numbers[start:end]
    body_sources = [p.source for p in pages][start:end]
    result.stats["body_pages"] = len(body)

    # --- S8 chunk ----------------------------------------------------------
    result.chunks = chunk_pages(
        body,
        chunk_chars=options.chunk_chars,
        overlap_chars=options.overlap_chars,
        filter_apparatus=options.filter_apparatus,
        exercise_page_ratio=options.exercise_page_ratio,
        profile=book,
        page_numbers=body_numbers,
        sources=body_sources,
    )

    # Counted here rather than inside the chunker so the comparison harness can
    # see it: routing collapsing from 16 pages to 1 was how the NCERT failure
    # was found in the first place.
    from .apparatus import page_is_exercise as _is_exercise

    result.stats.update({
        "exercise_pages": sum(
            1 for page in body
            if page.strip()
            and _is_exercise(
                [x for x in page.split("\n\n") if x.strip()],
                options.exercise_page_ratio, book,
            )
        ),
        "sources": len(sources),
        "skipped_sources": len(skipped),
        "pages": len(pages),
        "paragraphs": sum(len(p.paragraphs) for p in pages),
        "chunks": len(result.chunks),
        "chunks_per_page": round(len(result.chunks) / max(1, len(pages)), 2),
        "distinct_headings": len({c.heading for c in result.chunks if c.heading}),
        "table_chunks": sum(1 for c in result.chunks if c.kind == "table"),
    })

    if not result.chunks:
        raise UnusableBook(
            "The PDF produced no usable text after cleaning.",
            hint="The book may be an image-only scan, or entirely exercises.",
            code="no_chunks",
        )
    return result


def ingest_paths(paths: Sequence[str], options: Optional[IngestOptions] = None) -> IngestResult:
    """Ingest a list of PDF paths, in the order given."""
    return ingest(sources_from_paths(paths), options)


def ingest_dir(directory: str, options: Optional[IngestOptions] = None) -> IngestResult:
    """Ingest every PDF in a directory, sorted by name.

    The common NCERT shape: one file per chapter, named so that sorting puts
    them in reading order.
    """
    from pathlib import Path

    paths = sorted(str(p) for p in Path(directory).glob("*.pdf"))
    if not paths:
        raise UnusableBook(
            "No PDFs found in {}".format(directory), code="no_sources"
        )
    return ingest_paths(paths, options)
