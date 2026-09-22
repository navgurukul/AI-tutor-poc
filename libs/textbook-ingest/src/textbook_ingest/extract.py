"""S0 -- get text out of the PDFs, without letting one bad file sink the book.

The old pipeline called pypdf once for the whole upload and turned any failure
into a failed job. Measured against NCERT, that is too brittle: jesc109.pdf is a
legitimate 20 MB Class 10 Science chapter that trips pypdf's decompression-bomb
guard ("Limit reached while decompressing"), and under the old behaviour it cost
the other seventeen chapters of the book.

So extraction is per source and per page. A source that cannot be opened is
recorded and skipped; a page that cannot be read inside an otherwise fine source
becomes an empty page rather than an exception. What must never happen is a
chapter disappearing without the caller being told, so every loss is reported.
"""

import io
import logging
from typing import Iterable, List, Sequence, Tuple

from .errors import ExtractionError
from .types import Page, Source, Warning_

logger = logging.getLogger(__name__)


def _reader(data: bytes):
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - declared in [pdf] extra
        raise ExtractionError(
            "pypdf is not installed. Install textbook-ingest[pdf]."
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError("not readable as a PDF ({})".format(exc)) from exc

    if reader.is_encrypted:
        # An empty password unlocks the common "no printing" case. A real one is
        # a failure the user has to resolve, and saying so is more useful than
        # "could not read this file".
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ExtractionError(
                "password-protected; remove the password and try again"
            ) from exc
    return reader


def extract_source(source: Source) -> Tuple[List[str], List[Warning_]]:
    """Raw page text for one file, in reading order.

    Raises ExtractionError only when the file cannot be opened at all. A page
    that fails on its own is returned empty, with a warning -- one unreadable
    page in a chapter is not a reason to lose the chapter.
    """
    reader = _reader(source.data)
    pages: List[str] = []
    warnings: List[Warning_] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001 - one page must not end the file
            pages.append("")
            warnings.append(
                Warning_("page_unreadable", "page {} ({})".format(number, exc), source.name)
            )
    return pages, warnings


def extract(sources: Sequence[Source]) -> Tuple[List[Page], List[Warning_], List[str]]:
    """Every page of the book, plus what went wrong getting there.

    Returns (pages, warnings, skipped_source_names). Pages are numbered
    continuously across sources so a merged book and a per-chapter book behave
    the same downstream.
    """
    pages: List[Page] = []
    warnings: List[Warning_] = []
    skipped: List[str] = []

    for source in sources:
        try:
            raw_pages, page_warnings = extract_source(source)
        except ExtractionError as exc:
            # The whole chapter is gone. Keep going -- and say so loudly enough
            # that a caller cannot ship a corpus with a hole in it unnoticed.
            logger.warning("Skipping %s: %s", source.name, exc.detail)
            skipped.append(source.name)
            warnings.append(Warning_("source_skipped", exc.detail, source.name))
            continue

        warnings.extend(page_warnings)
        for raw in raw_pages:
            pages.append(Page(index=len(pages), source=source.name, raw=raw))

    return pages, warnings, skipped


def sources_from_paths(paths: Iterable[str]) -> List[Source]:
    """Convenience for the common case: a directory of chapter PDFs."""
    from pathlib import Path

    out: List[Source] = []
    for path in paths:
        p = Path(path)
        out.append(Source(name=p.name, data=p.read_bytes()))
    return out
