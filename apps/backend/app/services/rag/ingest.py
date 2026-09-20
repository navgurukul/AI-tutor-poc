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
from app.services.rag import pdf_text
from app.services.rag.retrieval import reset_pinned_cache
from app.services.rag.chunking import chunk_pages
from app.services.rag.embeddings import embed_documents
from app.services.rag.store import LibraryStore, StoreUnavailable

logger = logging.getLogger(__name__)

# Finished jobs are kept so the page can show the outcome after the fact, but
# not forever -- this is a POC, and the list is a UI convenience, not a record.
_MAX_REMEMBERED_JOBS = 40


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
        # like the text-quality ones below, is what closes that gap.
        warnings: List[str] = []
        removed = self.store.find_removed_by_hash(digest)
        if removed:
            warnings.append(
                "This exact file was already removed from the library once, on {} "
                "(was '{}', Class {} {}). Make sure this is the replacement you "
                "meant to upload, not the same file again.".format(
                    removed["removed_at"], removed["title"],
                    removed["grade"], removed["subject"],
                )
            )

        job.status = "extracting"
        job.stage_detail = "Reading and cleaning the PDF"
        # Extraction is synchronous and CPU-bound; off the event loop it would block
        # every chat request for the duration of a large book.
        pages, raw_page_count = await asyncio.to_thread(pdf_text.extract_and_clean, data)
        job.pages = raw_page_count

        if pdf_text.looks_like_scan(pages):
            job.status = "error"
            job.error = "No text layer found -- this looks like a scanned PDF."
            job.hint = (
                "Run it through OCR first (any tool that produces a searchable PDF), "
                "then upload the result."
            )
            return

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
            return

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
        if warnings:
            job.hint = " ".join(warnings)
            logger.warning("Ingesting %s with a warning: %s", job.filename, job.hint)

        chunks = chunk_pages(
            pages,
            target_chars=settings.rag_chunk_target_chars,
            overlap_chars=settings.rag_chunk_overlap_chars,
            max_chars=settings.rag_chunk_max_chars,
            min_chars=settings.rag_chunk_min_chars,
        )
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
        ) + (" -- warning: " + job.hint if warnings else "")
        logger.info(
            "Ingested %s (class %s %s): %d pages -> %d chunks in %.1fs",
            job.title, job.grade, job.subject, raw_page_count, job.chunks_done,
            time.time() - job.started_at,
        )
