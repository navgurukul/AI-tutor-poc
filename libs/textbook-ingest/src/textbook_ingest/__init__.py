"""textbook-ingest -- a school textbook PDF in, clean chunkable text out.

Built after measuring the same pipeline against eight textbooks from two
publishers (MSCERT and NCERT, Classes 1-10). The lesson that shaped the design:
the rules that generalised were the STRUCTURAL ones -- column measure, exercise
density, blank runs -- and the rules that broke were every regex that encoded
one publisher's vocabulary or typography. So the surface patterns are learned
from the document at ingest time, and only the structure is hard-coded.

    from textbook_ingest import ingest_dir

    result = ingest_dir("data/PDF NCERT/Class09-Science")
    print(result.stats["chunks"], "chunks")
    for warning in result.warnings:
        print("!", warning)
    for chunk in result.chunks:
        index(chunk.text, page=chunk.page_start)

The breadcrumb is the caller's decision and is off unless asked for, because it
was measured to inject wrong vocabulary into 47% of chunks and right vocabulary
into 43%:

    chunk.embedding_text()                        # prose alone (default)
    chunk.embedding_text(["Class 9", "Science"])  # prefixed, heading appended
"""

from .chunking import chunk_pages
from .errors import ExtractionError, TextbookIngestError, UnusableBook
from .extract import extract, sources_from_paths
from .pipeline import IngestOptions, ingest, ingest_dir, ingest_paths
from .profile import build_profile
from .types import BookProfile, Chunk, IngestResult, Page, Source, Warning_

__version__ = "0.1.0"

__all__ = [
    "ingest",
    "ingest_dir",
    "ingest_paths",
    "IngestOptions",
    "IngestResult",
    "Source",
    "Page",
    "Chunk",
    "BookProfile",
    "Warning_",
    "build_profile",
    "chunk_pages",
    "extract",
    "sources_from_paths",
    "TextbookIngestError",
    "ExtractionError",
    "UnusableBook",
    "__version__",
]
