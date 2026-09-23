"""Structural PDF ingestion: bytes in, retrieval-ready chunks out.

Ported from the `tutor-practice` prototype (2026-09-20) and resized for this
project's prompt budget. See `pipeline` for the stage order and the reasons it
is that order, and `chunk` for why the token target is what it is.

The public surface is deliberately two functions:

    analyze(data, meta)       stages 1-6, no Ollama, no database
    build_chunks(data, meta)  the whole pipeline, accepted chunks + report
"""

from .extract import PdfExtractionError
from .model import Chunk, Document
from .pipeline import analyze, build_chunks, warning_for

__all__ = [
    "Chunk",
    "Document",
    "PdfExtractionError",
    "analyze",
    "build_chunks",
    "warning_for",
]
