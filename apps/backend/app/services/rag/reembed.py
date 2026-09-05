"""Re-embedding the corpus under a different model, in the background.

This is the job that makes the embedding choice reversible rather than a
one-way door. The premise that made it look permanent was right as far as it
went -- vectors from two models are not comparable, and mixing them fails
silently -- but the conclusion did not follow, because `chunks.text` is already
on every device. Re-embedding reads data that is present locally. It is a
background job, not a redistribution.

The shape: build the new model's vec0 table alongside the old one, fill it from
stored text, and repoint `meta` only when every chunk is in. The old table goes
on serving queries the whole time, so the tutor stays answerable throughout and
a failure halfway leaves the library exactly as it was.

Cost is roughly one overnight run per device. That is the price of being able
to change your mind, and it is far below the price of not being able to.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.config import settings
from app.services.ollama_client import client
from app.services.rag.store import LibraryStore, StoreUnavailable, _serialise, vector_table_for

logger = logging.getLogger(__name__)

_MAX_REMEMBERED_JOBS = 10


@dataclass
class ReembedJob:
    """Same progress-polling shape as IngestJob, so the UI needs no new code."""

    id: str
    target_model: str
    target_dims: int
    target_table: str
    status: str = "queued"      # queued | embedding | swapping | done | error
    stage_detail: str = ""
    chunks_total: int = 0
    chunks_done: int = 0
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
            "target_model": self.target_model,
            "target_dims": self.target_dims,
            "target_table": self.target_table,
            "status": self.status,
            "stage_detail": self.stage_detail,
            "chunks_total": self.chunks_total,
            "chunks_done": self.chunks_done,
            "progress": round(self.progress, 3),
            "error": self.error,
            "hint": self.hint,
            "elapsed_seconds": round(
                (self.finished_at or time.time()) - self.started_at, 1
            ),
        }


class ReembedService:
    def __init__(self, store: LibraryStore):
        self.store = store
        self._jobs: Dict[str, ReembedJob] = {}
        # One at a time, and never alongside an ingestion: both saturate the
        # same CPU that Ollama needs to answer questions.
        self._lock = asyncio.Lock()

    def get(self, job_id: str) -> Optional[ReembedJob]:
        return self._jobs.get(job_id)

    def recent(self) -> List[ReembedJob]:
        return sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)

    def _remember(self, job: ReembedJob) -> None:
        self._jobs[job.id] = job
        if len(self._jobs) > _MAX_REMEMBERED_JOBS:
            for stale in sorted(self._jobs.values(), key=lambda j: j.started_at)[
                : len(self._jobs) - _MAX_REMEMBERED_JOBS
            ]:
                self._jobs.pop(stale.id, None)

    def start(self, *, model: str, dims: int) -> ReembedJob:
        job = ReembedJob(
            id=uuid.uuid4().hex[:12],
            target_model=model,
            target_dims=dims,
            target_table=vector_table_for(model),
        )
        self._remember(job)
        asyncio.create_task(self._run(job))
        return job

    async def _run(self, job: ReembedJob) -> None:
        async with self._lock:
            try:
                await self._reembed(job)
            except StoreUnavailable as exc:
                job.status, job.error, job.hint = "error", exc.detail, exc.hint
            except Exception as exc:  # noqa: BLE001 - a job must never die silently
                logger.exception("Re-embed failed for %s", job.target_model)
                job.status, job.error = "error", "Unexpected failure: {}".format(exc)
            finally:
                job.finished_at = time.time()

    async def _reembed(self, job: ReembedJob) -> None:
        if job.target_table == self.store.vector_table:
            job.status = "error"
            job.error = "The library is already embedded with {}.".format(
                job.target_model
            )
            return

        rows = await asyncio.to_thread(self.store.chunks_for_reembedding)
        if not rows:
            job.status = "done"
            job.stage_detail = "Nothing to re-embed."
            return

        job.chunks_total = len(rows)
        job.status = "embedding"
        job.stage_detail = "Re-embedding {} chunks with {}".format(
            len(rows), job.target_model
        )

        await asyncio.to_thread(
            self.store.create_vector_table, job.target_table, job.target_dims
        )

        batch_size = max(1, settings.rag_embed_batch_size)
        try:
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                vectors = await client.embed(
                    [r["embedding_text"] for r in batch], model=job.target_model
                )
                await asyncio.to_thread(
                    self.store.fill_vector_table, job.target_table, batch, vectors
                )
                job.chunks_done += len(batch)
        except Exception:
            # Leave the library exactly as it was. The old table never stopped
            # serving, so nothing the student can see has changed.
            await asyncio.to_thread(self.store.drop_vector_table, job.target_table)
            raise

        job.status = "swapping"
        job.stage_detail = "Cutting over to {}".format(job.target_table)
        # Only now does anything the tutor reads change, and it changes in one
        # transaction: meta repointed, old table dropped.
        await asyncio.to_thread(
            self.store.activate_vector_table,
            job.target_table,
            job.target_model,
            job.target_dims,
        )
        job.status = "done"
        job.stage_detail = "Serving from {}".format(job.target_table)
        logger.info(
            "Re-embed complete: %d chunks now served from %s (%s, %d dims)",
            job.chunks_done,
            job.target_table,
            job.target_model,
            job.target_dims,
        )
