"""Setup-page API: upload textbooks, watch ingestion, manage the library."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import settings
from app.services.rag import service
from app.services.rag.store import StoreUnavailable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/library", tags=["library"])


def _require_store() -> None:
    """Turn an unopened store into a 503 that says how to fix it."""
    if not settings.rag_enabled:
        raise HTTPException(
            status_code=503,
            detail="Textbook retrieval is disabled (set RAG_ENABLED=true to use it).",
        )
    if not service.store.is_open:
        reason = service.store.unavailable_reason
        raise HTTPException(
            status_code=503,
            detail=(reason.detail if reason else "The textbook library is unavailable.")
            + ((" " + reason.hint) if reason and reason.hint else ""),
        )


@router.get("/status", summary="Library status and coverage")
async def library_status() -> Dict[str, Any]:
    return service.status()


@router.get("/documents", summary="Ingested textbooks")
async def list_documents() -> Dict[str, Any]:
    _require_store()
    return {"documents": service.store.list_documents()}


@router.post("/documents", status_code=202, summary="Upload a PDF and start ingestion")
async def upload_document(
    file: UploadFile = File(...),
    grade: int = Form(...),
    subject: str = Form(...),
    title: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """Accepts the PDF, starts a background job and returns its id.

    202 rather than 201: nothing is in the library yet when this returns. A
    textbook takes minutes to embed on the target hardware, so the response
    carries a job to poll instead of the finished document.
    """
    _require_store()

    if not 1 <= grade <= 12:
        raise HTTPException(status_code=422, detail="Grade must be between 1 and 12.")
    subject = (subject or "").strip()
    if not subject:
        raise HTTPException(status_code=422, detail="Subject is required.")

    filename = file.filename or "textbook.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files can be ingested.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")
    limit = settings.rag_max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(
            status_code=413,
            detail="File is {:.1f} MB; the limit is {} MB.".format(
                len(data) / 1024 / 1024, settings.rag_max_upload_mb
            ),
        )

    job = service.ingestion.start(
        data=data,
        filename=filename,
        title=(title or "").strip() or filename.rsplit(".", 1)[0],
        grade=grade,
        subject=subject,
    )
    return {"job": job.as_dict()}


@router.get("/jobs", summary="Recent ingestion jobs")
async def list_jobs() -> Dict[str, Any]:
    return {"jobs": [j.as_dict() for j in service.ingestion.recent()]}


@router.get("/jobs/{job_id}", summary="Ingestion progress")
async def job_status(job_id: str) -> Dict[str, Any]:
    job = service.ingestion.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such ingestion job.")
    return {"job": job.as_dict()}


@router.delete("/documents/{document_id}", summary="Remove a textbook")
async def delete_document(document_id: int) -> Dict[str, Any]:
    _require_store()
    try:
        removed = service.store.delete_document(document_id)
    except StoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=exc.detail)
    if not removed:
        raise HTTPException(status_code=404, detail="No such document.")
    return {"deleted": True, "id": document_id}


@router.post("/search", summary="Search the library (debugging aid)")
async def search(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Runs retrieval without the model.

    Exposed because when the tutor gives a poor answer, the first question is
    always whether retrieval found the right passage or the model ignored it,
    and this separates the two.

    Send `previous_question` to search the way a follow-up turn does. Hits come
    back best-first; `in_prompt` marks the ones a chat turn would actually
    put in front of the model -- the first rag_top_k, less any the character
    budget cuts -- because a passage can be retrieved and still never be read.
    `context_max_chars` sets that budget as a chat request's own field does,
    so a benchmark sweeping it scores each arm against the prompt that arm
    actually built.
    """
    _require_store()
    from app.services.rag.retrieval import (
        citations,
        retrieval_query,
        retrieve,
        within_budget,
    )

    question = str(payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="A question is required.")
    previous = str(payload.get("previous_question") or "").strip() or None
    hits = await retrieve(
        service.store,
        question,
        grade=payload.get("grade"),
        subject=payload.get("subject"),
        k=int(payload.get("k") or settings.rag_top_k),
        previous_question=previous,
    )
    budget = payload.get("context_max_chars")
    read = len(within_budget(hits[: settings.rag_top_k], int(budget) if budget else None))
    return {
        "question": question,
        "query_carried": retrieval_query(question, previous) != question,
        "hits": citations(hits),
        "excerpts": [h.text for h in hits],
        "in_prompt": [i < read for i in range(len(hits))],
    }
