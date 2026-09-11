"""In-memory conversation store.

A POC deliberately keeps this in process memory: no database, nothing to
install, and restarting the server resets the demo. Swap this class for a
Redis/SQLite implementation if the POC graduates.
"""

import asyncio
import re
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.config import settings
from app.schemas import Message, TutorProfile


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Split on sentence enders followed by whitespace. Good enough for tutor prose;
# it does not need to survive "e.g." because it only ever picks the LAST piece.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _closing_sentence(text: str, max_chars: int) -> str:
    """The last complete sentence of a reply -- the socratic nudge.

    The end is what matters, not the start: the question the student is
    answering is the final clause. So an over-long trailing paragraph is cut
    from the FRONT, on a word boundary, rather than truncated at the tail like
    ordinary prose would be.
    """
    text = (text or "").strip()
    if not text:
        return ""
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    if not parts:
        return ""
    last = parts[-1]
    if len(last) > max_chars:
        tail = last[-max_chars:]
        last = "\u2026" + (tail.split(" ", 1)[-1] if " " in tail else tail)
    return last


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

    def history(
        self,
        questions: int,
        keep_nudge: bool = False,
        nudge_max_chars: int = 200,
    ) -> List[Dict[str, str]]:
        """What the MODEL re-reads, shaped for Ollama's /api/chat.

        Deliberately not the same thing as what the student sees. The full
        reply stays in self.messages, streams to the UI and is returned by the
        API; only this view is abridged. Those two were one string until they
        were measured, and the previous answer coming back in full cost ~3.9s
        of prefill on every turn after the first -- answer length charged
        twice, once to generate and again to re-read.

        Replayed: the last `questions` student questions, the closing sentence
        of the most recent reply when `keep_nudge` (socratic style ends every
        answer by inviting the student to think, so their next message is often
        a reply to it), and the current question. The body of the previous
        answer -- worked example, elaboration -- is dropped; nothing refers
        back to it.

        Not a flat "last N messages" window any more, which is why the setting
        that drives it was renamed. Order is chronological, so the nudge sits
        between the question that produced it and the reply to it.
        """
        if not self.messages:
            return []
        last = len(self.messages) - 1
        keep = {last}                      # the current question, always
        seen = 0
        nudge_at = None
        for i in range(last - 1, -1, -1):
            m = self.messages[i]
            if m.role == "user" and seen < questions:
                keep.add(i)
                seen += 1
            elif m.role == "assistant" and keep_nudge and nudge_at is None:
                nudge_at = i
                keep.add(i)
            if seen >= questions and (nudge_at is not None or not keep_nudge):
                break

        out: List[Dict[str, str]] = []
        for i in sorted(keep):
            m = self.messages[i]
            content = m.content
            if i == nudge_at:
                content = _closing_sentence(content, nudge_max_chars)
                if not content:
                    continue          # nothing quotable; drop the turn entirely
            out.append({"role": m.role, "content": content})
        return out

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
