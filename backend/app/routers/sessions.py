"""Conversation session management.

Sessions are created implicitly by /api/chat, so these endpoints exist for a
sidebar/history UI: list them, replay a transcript, clear one.
"""

from typing import List

from fastapi import APIRouter, HTTPException, Path

from app.schemas import (
    DeleteResponse,
    SessionCreateRequest,
    SessionDetail,
    SessionSummary,
)
from app.services.sessions import Session, store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _summary(session: Session) -> SessionSummary:
    return SessionSummary(
        session_id=session.session_id,
        profile=session.profile,
        message_count=len(session.messages),
        created_at=session.created_at,
        updated_at=session.updated_at,
        preview=session.preview,
    )


@router.post("", response_model=SessionSummary, summary="Start a session explicitly")
async def create_session(request: SessionCreateRequest) -> SessionSummary:
    """Optional: pre-create a session with a tutor profile. Posting to /api/chat
    without a session_id does the same thing implicitly."""
    return _summary(await store.create(request.profile))


@router.get("", response_model=List[SessionSummary], summary="List active sessions")
async def list_sessions() -> List[SessionSummary]:
    return [_summary(s) for s in await store.list()]


@router.get("/{session_id}", response_model=SessionDetail, summary="Full transcript")
async def get_session(session_id: str = Path(...)) -> SessionDetail:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    return SessionDetail(**_summary(session).model_dump(), messages=session.messages)


@router.delete("/{session_id}", response_model=DeleteResponse, summary="Delete a session")
async def delete_session(session_id: str = Path(...)) -> DeleteResponse:
    return DeleteResponse(session_id=session_id, deleted=await store.delete(session_id))
