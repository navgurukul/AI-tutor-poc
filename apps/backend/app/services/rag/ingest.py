"""The ingestion pipeline: PDF bytes in, embedded chunks out.

Ingestion is slow by nature -- a 150-page textbook is a few hundred embedding
calls, and on the oldest target laptops that is minutes, not seconds. So an
upload does not block on it. The request stores the file, starts a background
job and returns an id; the setup page polls that id for progress. This is also
why progress is reported in chunks rather than a spinner: a job that will take
four minutes needs to show that it is advancing.
"""

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.config import settings
from app.services.ollama_client import OllamaError
from app.services.rag import ingestion, pdf_text
from app.services.rag.retrieval import reset_pinned_cache
from app.services.rag.chunking import chunk_pages
from app.services.rag.embeddings import embed_documents
from app.services.rag.store import LibraryStore, StoreUnavailable

logger = logging.getLogger(__name__)

# Finished jobs are kept so the page can show the outcome after the fact, but
# not forever -- this is a POC, and the list is a UI convenience, not a record.
_MAX_REMEMBERED_JOBS = 40


@dataclass
class _StoredChunk:
    """A pipeline chunk in the shape the store and the embedder expect.

    An adapter rather than a change to either side: `chunking.Chunk` and
    `ingestion.model.Chunk` are both right for their own pipeline, and while
    `rag_structural_ingestion` can be switched off, both have to reach
    `store.add_chunks` through one interface.
    """

    ordinal: int
    text: str
    heading: str
    page_start: int
    page_end: int
    content_type: str = ""
    section: str = ""

    def embedding_text(self, grade: int, subject: str) -> str:
        """What actually gets embedded: breadcrumb, then prose.

        Byte-identical in format to `chunking.Chunk.embedding_text`, and that
        is load-bearing rather than tidy. The per-language ceilings in config
        (rag_ceiling_en/hi/mr) were calibrated against distances produced with
        THIS breadcrumb in front of the text. Change the separator or the
        field order and every distance shifts, so the gate is silently
        miscalibrated and the only symptom is a tutor that abstains more, or
        less, than it should.
        """
        crumbs = ["Class {}".format(grade), subject]
        if self.heading:
            crumbs.append(self.heading)
        return "{}\n\n{}".format(" > ".join(crumbs), self.text)


@dataclass
class IngestJob:
    id: str
    filename: str
    title: str
    grade: int
    subject: str
    language: str = ""
    status: str = "queued"          # queued | extracting | embedding | done | error
    stage_detail: str = ""
    pages: int = 0
    chunks_total: int = 0
    chunks_done: int = 0
    document_id: Optional[int] = None
    error: Optional[str] = None
    hint: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    @property
    def progress(self) -> float:
        if self.status == "done":
            return 1.0
        if not self.chunks_total:
            return 0.0
        return min(0.99, self.chunks_done / self.chunks_total)

    def as_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "grade": self.grade,
            "subject": self.subject,
            "language": self.language,
            "status": self.status,
            "stage_detail": self.stage_detail,
            "pages": self.pages,
            "chunks_total": self.chunks_total,
            "chunks_done": self.chunks_done,
            "progress": round(self.progress, 3),
            "document_id": self.document_id,
            "error": self.error,
            "hint": self.hint,
            "elapsed_seconds": round(
                (self.finished_at or time.time()) - self.started_at, 1
            ),
        }


class IngestionService:
    def __init__(self, store: LibraryStore):
        self.store = store
        self._jobs: Dict[str, IngestJob] = {}
        # One ingestion at a time. Two concurrent jobs would compete for the
        # same CPU that Ollama needs to answer questions, and on a dual-core
        # laptop that makes the tutor unusable while a book loads.
        self._lock = asyncio.Lock()

    def get(self, job_id: str) -> Optional[IngestJob]:
        return self._jobs.get(job_id)

    def recent(self) -> List[IngestJob]:
        return sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)

    def _remember(self, job: IngestJob) -> None:
        self._jobs[job.id] = job
        if len(self._jobs) > _MAX_REMEMBERED_JOBS:
            for stale in sorted(self._jobs.values(), key=lambda j: j.started_at)[
                : len(self._jobs) - _MAX_REMEMBERED_JOBS
            ]:
                self._jobs.pop(stale.id, None)

    def start(
        self,
        *,
        data: bytes,
        filename: str,
        title: str,
        grade: int,
        subject: str,
        language: str = "",
    ) -> IngestJob:
        job = IngestJob(
            id=uuid.uuid4().hex[:12],
            filename=filename,
            title=title or filename,
            grade=grade,
            subject=subject,
            language=language,
        )
        self._remember(job)
        asyncio.create_task(self._run(job, data))
        return job

    async def _run(self, job: IngestJob, data: bytes) -> None:
        async with self._lock:
            try:
                await self._ingest(job, data)
            except StoreUnavailable as exc:
                job.status, job.error, job.hint = "error", exc.detail, exc.hint
            except pdf_text.PdfExtractionError as exc:
                job.status, job.error = "error", str(exc)
            except OllamaError as exc:
                job.status, job.error, job.hint = "error", exc.detail, exc.hint
            except Exception as exc:  # noqa: BLE001 - a job must never die silently
                logger.exception("Ingestion failed for %s", job.filename)
                job.status, job.error = "error", "Unexpected failure: {}".format(exc)
            finally:
                job.finished_at = time.time()

    # -- chunk production --------------------------------------------------
    #
    # Both paths return (chunks, page_count, warning), or (None, 0, "") when
    # they have already failed the job. Both run in a worker thread: they are
    # synchronous and CPU-bound, and on the event loop they would block every
    # chat request for the length of a book.

    def _structural_chunks(self, job: IngestJob, data: bytes):
        """The 8-stage pipeline: geometry, classification, validation."""
        chunks, report = ingestion.build_chunks(
            data,
            {
                "file_name": job.filename,
                "subject": job.subject,
                "grade": job.grade,
                "medium": job.language,
            },
        )

        verdict = report["validate"]["verdict"]
        if not verdict["usable"] and settings.rag_reject_unusable_documents:
            # The one case where an upload is refused. A document whose text
            # layer is unreadable does not produce a poor book, it produces a
            # book that answers nothing -- and stored, it is indistinguishable
            # from the tutor simply being bad. See validate._verdict.
            job.status = "error"
            job.error = verdict["message"]
            job.hint = (
                "Run it through OCR first (any tool that produces a searchable "
                "PDF), then upload the result."
                if verdict["reason"] in ("no_text", "unreadable_text_layer")
                else None
            )
            logger.warning(
                "Refused %s: %s (%s)", job.filename, verdict["reason"], verdict["message"]
            )
            return None, 0, ""

        logger.info(
            "%s: %d pages (%d two-column) -> %d chunks, median %d tokens, "
            "%d over the %d-token cap; types %s",
            job.filename,
            report["extract"]["pages"],
            report["layout"]["two_column"],
            len(chunks),
            report["chunk"]["tokens"]["median"],
            report["chunk"]["tokens"]["over_cap"],
            report["chunk"]["tokens"]["cap"],
            report["chunk"]["by_type"],
        )
        adapted = [
            _StoredChunk(
                ordinal=index,
                text=chunk.text,
                heading=chunk.section,
                page_start=chunk.page,
                page_end=chunk.page_end,
                content_type=chunk.content_type,
                section=chunk.section,
            )
            for index, chunk in enumerate(chunks)
        ]
        return adapted, report["extract"]["pages"], ingestion.warning_for(report)

    def _legacy_chunks(self, job: IngestJob, data: bytes):
        """The line-statistical chunker this port replaces.

        Kept behind `rag_structural_ingestion` so the two can be compared on
        the same PDF. It produces different chunk boundaries, so a library
        holding some of each retrieves from both with no way to tell which
        chunker produced a bad answer -- switch, then re-ingest everything.
        """
        pages, raw_page_count = pdf_text.extract_and_clean(data)

        if pdf_text.looks_like_scan(pages):
            job.status = "error"
            job.error = "No text layer found -- this looks like a scanned PDF."
            job.hint = (
                "Run it through OCR first (any tool that produces a searchable PDF), "
                "then upload the result."
            )
            return None, 0, ""

        warnings: List[str] = []
        # A text layer that exists but is a symbol/dingbat font's glyph IDs,
        # not real characters, is functionally the same failure as no text
        # layer at all -- unlike looks_mis_decoded below, there is nothing
        # here worth storing with a caveat, so this refuses rather than warns.
        if pdf_text.looks_like_garbage_script(pages):
            job.status = "error"
            job.error = (
                "The text layer in this PDF does not decode to readable characters "
                "-- likely a legacy or symbol font without a usable character map."
            )
            job.hint = (
                "Run it through OCR first (any tool that produces a searchable PDF "
                "in a normal font), then upload the result."
            )
            return None, 0, ""

        # Mis-decoded Devanagari is the one failure that looks like success.
        # The text has the right script and the right length, it embeds without
        # complaint, and it retrieves nothing -- so the only symptom is a tutor
        # that is vaguely bad in Hindi, which is indistinguishable from the
        # model being bad in Hindi. It is named here, where the cause is still
        # visible, rather than left to become a fortnight of prompt tuning.
        #
        # But uploads are never refused for text quality -- the person uploading
        # has no other copy of the book, and a refusal just moves the problem to
        # them. Legacy Chanakya/Kruti fonts are converted during extraction
        # (legacy_hindi); anything still wrong is stored WITH a warning, so the
        # setup page says why answers from this book may be poor.
        if pdf_text.looks_mis_decoded(pages):
            rate = pdf_text.devanagari_breakage_rate(pages)
            warnings.append((
                "Some Hindi text did not extract cleanly ({:.1f} broken letters per "
                "100 characters); answers from this book may be less accurate."
            ).format(rate or 0.0))
        elif (job.language or "").strip().lower() in ("hindi", "marathi") and \
                pdf_text.devanagari_share(pages) < 0.2:
            warnings.append(
                "Very little Hindi text came out of this PDF -- it may use an old "
                "font that could not be converted. Answers from it may be poor."
            )
        warning = " ".join(warnings)

        chunks = chunk_pages(
            pages,
            target_chars=settings.rag_chunk_target_chars,
            overlap_chars=settings.rag_chunk_overlap_chars,
            max_chars=settings.rag_chunk_max_chars,
            min_chars=settings.rag_chunk_min_chars,
        )
        return chunks, raw_page_count, warning

    async def _ingest(self, job: IngestJob, data: bytes) -> None:
        digest = hashlib.sha256(data).hexdigest()
        existing = self.store.find_by_hash(digest)
        if existing:
            job.status = "error"
            job.error = "This exact PDF is already in the library as '{}' (Class {} {}).".format(
                existing["title"], existing["grade"], existing["subject"]
            )
            job.hint = "Delete it first if you want to re-ingest."
            return

        # Not blocked, unlike the check above -- deleting a document, then
        # re-uploading the identical file, is sometimes exactly what you mean
        # to do (undoing a mistaken delete). What it cannot be is silent: the
        # hash-dedup above only ever sees documents still present, so once
        # the original is gone this is the only thing that can still say
        # "you have seen this exact file before." A warning here, surfaced
        # like the text-quality ones, is what closes that gap.
        removed_warning = ""
        removed = self.store.find_removed_by_hash(digest)
        if removed:
            removed_warning = (
                "This exact file was already removed from the library once, on {} "
                "(was '{}', Class {} {}). Make sure this is the replacement you "
                "meant to upload, not the same file again.".format(
                    removed["removed_at"], removed["title"],
                    removed["grade"], removed["subject"],
                )
            )

        job.status = "extracting"
        job.stage_detail = "Reading and cleaning the PDF"

        if settings.rag_structural_ingestion:
            chunks, raw_page_count, warning = await asyncio.to_thread(
                self._structural_chunks, job, data
            )
            if chunks is None:
                return  # job already carries the error and the hint
        else:
            chunks, raw_page_count, warning = await asyncio.to_thread(
                self._legacy_chunks, job, data
            )
            if chunks is None:
                return

        job.pages = raw_page_count
        warning = " ".join(w for w in (removed_warning, warning) if w)
        if warning:
            job.hint = warning
            logger.warning("Ingesting %s with a warning: %s", job.filename, warning)

        if not chunks:
            job.status = "error"
            job.error = "The PDF produced no usable text after cleaning."
            return

        job.chunks_total = len(chunks)
        job.status = "embedding"
        job.stage_detail = "Embedding {} chunks".format(len(chunks))

        document_id = self.store.add_document(
            filename=job.filename,
            title=job.title,
            grade=job.grade,
            subject=job.subject,
            language=job.language,
            sha256=digest,
            pages=raw_page_count,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        job.document_id = document_id

        batch_size = max(1, settings.rag_embed_batch_size)
        try:
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start : start + batch_size]
                vectors = await embed_documents(
                    [c.embedding_text(job.grade, job.subject) for c in batch],
                    model=self.store.embedding_model,
                )
                await asyncio.to_thread(
                    self.store.add_chunks,
                    document_id,
                    job.grade,
                    job.subject,
                    list(zip(batch, vectors)),
                    job.language,
                )
                job.chunks_done += len(batch)
        except Exception:
            # A half-embedded book is worse than no book: it retrieves from the
            # first few chapters only, and looks like the tutor simply does not
            # know the rest. Roll the whole document back.
            await asyncio.to_thread(self.store.delete_document, document_id)
            job.document_id = None
            raise

        job.status = "done"
        # The pinned block is memoised per (grade, subject, medium) and would
        # otherwise keep serving the library as it was before this upload — the
        # new book simply would not appear until the backend restarted.
        reset_pinned_cache()
        job.stage_detail = "Added {} chunks from {} pages".format(
            job.chunks_done, raw_page_count
        ) + (" -- warning: " + job.hint if warning else "")
        logger.info(
            "Ingested %s (class %s %s): %d pages -> %d chunks in %.1fs",
            job.title, job.grade, job.subject, raw_page_count, job.chunks_done,
            time.time() - job.started_at,
        )
