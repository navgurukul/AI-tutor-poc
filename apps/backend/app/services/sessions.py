"""In-memory conversation store.

A POC deliberately keeps this in process memory: no database, nothing to
install, and restarting the server resets the demo. Swap this class for a
Redis/SQLite implementation if the POC graduates.
"""

import asyncio
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.config import settings
from app.schemas import Message, TutorProfile


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Session:
    def __init__(self, session_id: str, profile: Optional[TutorProfile] = None):
        self.session_id = session_id
        self.profile = profile or TutorProfile()
        self.messages: List[Message] = []
        self.created_at = _now()
        self.updated_at = self.created_at

    def add(self, role: str, content: str) -> Message:
        message = Message(role=role, content=content, created_at=_now())
        self.messages.append(message)
        self.updated_at = message.created_at
        return message

    def pop_last(self) -> None:
        """Undo the most recent message.

        Used to roll back the student's turn when generation fails, so a retry
        does not leave two user messages in a row in the history.
        """
        if self.messages:
            self.messages.pop()
            self.updated_at = self.messages[-1].created_at if self.messages else self.created_at

    def previous_question(self) -> Optional[str]:
        """The question before the one being answered, if there is one.

        Retrieval needs it for a follow-up that names no topic of its own. The
        current turn is already appended by the time this is called, so the
        search starts one behind it.
        """
        for message in reversed(self.messages[:-1]):
            if message.role == "user":
                return message.content
        return None

    def history(self, limit: int) -> List[Dict[str, str]]:
        """The last `limit` messages, shaped for Ollama's /api/chat."""
        recent = self.messages[-limit:] if limit > 0 else self.messages
        return [{"role": m.role, "content": m.content} for m in recent]

    @property
    def preview(self) -> Optional[str]:
        for message in self.messages:
            if message.role == "user":
                return message.content[:120]
        return None

    def is_expired(self) -> bool:
        ttl = timedelta(minutes=settings.session_ttl_minutes)
        return _now() - self.updated_at > ttl


class SessionStore:
    """Async-safe LRU store with TTL eviction."""

    def __init__(self) -> None:
        self._sessions: "OrderedDict[str, Session]" = OrderedDict()
        self._lock = asyncio.Lock()

    async def create(self, profile: Optional[TutorProfile] = None) -> Session:
        async with self._lock:
            self._prune_locked()
            session = Session(uuid.uuid4().hex, profile)
            self._sessions[session.session_id] = session
            while len(self._sessions) > settings.max_sessions:
                self._sessions.popitem(last=False)  # drop least recently used
            return session

    async def get(self, session_id: str) -> Optional[Session]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.is_expired():
                del self._sessions[session_id]
                return None
            self._sessions.move_to_end(session_id)
            return session

    async def get_or_create(
        self, session_id: Optional[str], profile: Optional[TutorProfile] = None
    ) -> Session:
        """Resolve a session id, creating one when it is missing or expired.

        An unknown id yields a fresh session rather than a 404 so a frontend
        holding a stale id after a server restart keeps working.
        """
        if session_id:
            session = await self.get(session_id)
            if session is not None:
                if profile is not None:
                    session.profile = profile
                return session
        return await self.create(profile)

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None

    async def list(self) -> List[Session]:
        async with self._lock:
            self._prune_locked()
            return sorted(
                self._sessions.values(), key=lambda s: s.updated_at, reverse=True
            )

    async def count(self) -> int:
        async with self._lock:
            self._prune_locked()
            return len(self._sessions)

    def _prune_locked(self) -> None:
        for key in [k for k, v in self._sessions.items() if v.is_expired()]:
            del self._sessions[key]


store = SessionStore()
