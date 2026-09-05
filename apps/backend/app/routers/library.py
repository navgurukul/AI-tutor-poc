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
    language: Optional[str] = Form(None),
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
        language=(language or "").strip(),
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


@router.post("/reembed", status_code=202, summary="Re-embed the library with another model")
async def start_reembed(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild the vectors under a different embedding model, in the background.

    The tutor keeps answering from the current table throughout; the cutover
    happens in one transaction when the last chunk is in. This is what makes
    the embedding choice reversible -- and, until it has been run on a
    populated library at least once, it is only reversible in principle.
    """
    _require_store()
    model = (payload.get("model") or "").strip()
    if not model:
        raise HTTPException(status_code=422, detail="A model name is required.")
    dims = payload.get("dims")
    if not isinstance(dims, int) or dims <= 0:
        raise HTTPException(
            status_code=422, detail="dims must be the vector width of that model."
        )
    job = service.reembedding.start(model=model, dims=dims)
    return {"job": job.as_dict()}


@router.get("/reembed/jobs", summary="Recent re-embed jobs")
async def list_reembed_jobs() -> Dict[str, Any]:
    return {"jobs": [j.as_dict() for j in service.reembedding.recent()]}


@router.get("/reembed/jobs/{job_id}", summary="Re-embed progress")
async def reembed_job_status(job_id: str) -> Dict[str, Any]:
    job = service.reembedding.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")
    return {"job": job.as_dict()}


@router.post("/search", summary="Search the library (debugging aid)")
async def search(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Runs retrieval without the model.

    Exposed because when the tutor gives a poor answer, the first question is
    always whether retrieval found the right passage or the model ignored it,
    and this separates the two. The evaluation harness is built on this route
    for the same reason -- it measures retrieval, not generation.

    `language` is the session language the gate should use. `raw` returns the
    ungated dense leg with its distances, which is what calibration needs.
    """
    _require_store()
    from app.services.rag.embeddings import embed_query
    from app.services.rag.gate import resolve_query_language
    from app.services.rag.query import build_match_query
    from app.services.rag.retrieval import citations, retrieve

    question = str(payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="A question is required.")

    grade = payload.get("grade")
    language = payload.get("language")
    k = int(payload.get("k") or settings.rag_top_k)

    if payload.get("raw"):
        # Ungated, so the on-topic and off-topic distance distributions can be
        # read off directly. Every ceiling in config is a starting point until
        # this has been run against a golden set.
        # The store's model, not config's -- see embeddings.embed_query.
        vector = await embed_query(question, model=service.store.embedding_model)
        hits = service.store.search(
            vector, grade=grade, subject=None, k=int(payload.get("candidates") or 50)
        )
        return {
            "question": question,
            "query_language": resolve_query_language(language, question),
            "match_query": build_match_query(question),
            "hits": citations(hits),
        }

    hits = await retrieve(
        service.store, question, grade=grade, k=k, language=language
    )
    return {
        "question": question,
        "query_language": resolve_query_language(language, question),
        "match_query": build_match_query(question),
        "hits": citations(hits),
        "excerpts": [h.text for h in hits],
    }
