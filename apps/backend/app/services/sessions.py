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
from app.services.rag.followup import is_context_dependent
from app.services.tutor import follow_up_message


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Session:
    def __init__(self, session_id: str, profile: Optional[TutorProfile] = None):
        self.session_id = session_id
        self.profile = profile or TutorProfile()
        self.messages: List[Message] = []
        # What each passage was sent as on the last turn, by chunk id. A
        # follow-up that retrieves the same passage sends it again verbatim
        # instead of re-shortened around its own words, so its prompt still
        # starts with the last one and Ollama's cache covers it (see
        # retrieval.prompt_hits). Replaced every turn, so it never grows.
        self.excerpts: Dict[int, str] = {}
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

    def earlier_questions(self, questions: int) -> List[str]:
        """The earlier questions the current one leans on, oldest first.

        Empty unless the current question points outside itself -- "How can we
        reduce it?" -- by the same word test retrieval uses to decide whether
        to search with the previous question (rag.followup). A question that
        names its own topic carries nothing, which is most of them.
        """
        if questions <= 0 or not self.messages:
            return []
        current = self.messages[-1]
        if current.role != "user" or not is_context_dependent(current.content):
            return []
        earlier = [m.content for m in reversed(self.messages[:-1]) if m.role == "user"]
        return earlier[:questions][::-1]

    def history(self, questions: int) -> List[Dict[str, str]]:
        """What the MODEL reads of the conversation, shaped for /api/chat.

        Deliberately not the same thing as what the student sees. The full
        reply stays in self.messages, streams to the UI and is returned by the
        API; only this view is abridged. Those two were one string until they
        were measured, and the previous answer coming back in full cost ~3.9s
        of prefill on every turn after the first -- answer length charged
        twice, once to generate and again to re-read.

        Always exactly one student message, and never an assistant turn:

          a question that names its topic   the question, as asked
          a follow-up ("how can we reduce   the question with the last
          it?", "why?")                     `questions` questions before it
                                            named as background, and the
                                            style rule's length spelled out
                                            (tutor.FOLLOW_UP_PROMPT)

        Replaying earlier turns as chat turns failed three ways on a 1.5B
        model, all measured live. Two student turns in a row read as one request
        and got both answered: "What is magnetic force?" opened with the answer
        to the shadow question before it. A fixed "(answered)" assistant turn
        between them was copied as the whole reply on 7 of 12 pronoun
        follow-ups. The opening sentence of the real answer stopped both, but
        the model matched its length: 6 of 6 topic switches came back as a
        single sentence, against 1 of 6 without it. A model imitates its own
        last turn, so this gives it none to imitate.

        A new topic carries nothing because it needs nothing, and carrying the
        old question is exactly what got it answered.

        Against the opening-sentence version on the shipped Class 6 corpus (Mac,
        2 reps): topic switches answered in one sentence 5/6 -> 1/6 (the same
        questions in a fresh session: 1-2/6), follow-ups 17/32 -> 9/32, none
        answered the old topic, none copied anything. Prompt tokens for a new
        topic 323 -> 294, for a follow-up 327 -> 338.
        """
        if not self.messages:
            return []
        current = self.messages[-1]
        earlier = self.earlier_questions(questions)
        content = (
            follow_up_message(earlier, current.content, self.profile.style)
            if earlier
            else current.content
        )
        return [{"role": current.role, "content": content}]

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
