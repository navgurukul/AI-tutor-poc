"""In-memory conversation store.

A POC deliberately keeps this in process memory: no database, nothing to
install, and restarting the server resets the demo. Swap this class for a
Redis/SQLite implementation if the POC graduates.
"""

import asyncio
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.config import settings
from app.schemas import Message, TutorProfile


@dataclass
class PreparedPassage:
    """A passage read into Ollama's cache while the student was still typing
    or speaking, waiting to be claimed by whatever question actually arrives.

    Built by `POST /api/chat/prepare` from a draft the student hasn't sent yet,
    so it can be wrong or stale -- the asker re-retrieves on the real question
    and only reuses this when the passages still match (see chat.py). Never
    required for correctness: a miss just falls back to the normal single-
    message turn, at the normal cost.
    """

    chunk_ids: List[int]
    block: str                       # the passage text, as its own user turn
    ack: str                         # the fixed tutor reply that closes it
    # How many of THIS session's messages existed when the prime was built.
    # The real ask must be extending exactly that prefix -- if the student's
    # history moved (an earlier prime claimed, a message added some other
    # way) the messages this was primed against no longer exist, and reusing
    # it would build a prompt Ollama has never seen a prefix of.
    history_len: int
    started_at: float = field(default_factory=time.monotonic)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Session:
    def __init__(self, session_id: str, profile: Optional[TutorProfile] = None):
        self.session_id = session_id
        self.profile = profile or TutorProfile()
        self.messages: List[Message] = []
        self.created_at = _now()
        self.updated_at = self.created_at
        # Chunk ids retrieved so far this session, in the order they arrived.
        #
        # Each passage is pasted into the conversation once (rag_dedup_context):
        # a chunk that arrived on an earlier turn is still in the conversation a
        # few messages up, so sending it again would only add new prompt tokens
        # -- ~38 ms each on this CPU -- to say something the model can already
        # read. A follow-up on the same topic therefore adds no passage at all.
        self.context_chunk_ids: List[int] = []
        # The passages the most recent question was answered from (empty when it
        # was answered without the library). A follow-up like "give an example of
        # this" is about these, and they are already in the conversation.
        self.last_hit_ids: List[int] = []
        # A passage read into Ollama's cache from a draft the student hasn't
        # sent yet (see PreparedPassage). One at a time: a second prepare
        # replaces it, and claiming it (or the session moving on without it)
        # clears it -- there is never a queue of guesses to reconcile.
        self.prepared: Optional[PreparedPassage] = None
        # How many prepares have been DISPATCHED for this session, ever.
        # Two prepares can be in flight at once (the student kept typing), and
        # they are not guaranteed to finish in the order they started -- the
        # second draft might retrieve and prime faster than the first. Each
        # call captures its own number at dispatch and only writes
        # `self.prepared` if no NEWER call has been dispatched since, so the
        # result that lands is always the one for the most recent draft,
        # regardless of which finished first.
        self.prepare_seq: int = 0
        # The in-flight prepare task, if one is running right now -- set by
        # the /api/chat/prepare endpoint at dispatch, cleared when it finishes
        # (only by itself; see that endpoint for why a stale clear is a bug).
        #
        # Exists so a real question that arrives a moment too early -- while
        # its own passage is still being read into the cache -- can wait a
        # BOUNDED moment for it instead of missing by a hair and paying full
        # price. Measured 2026-09-14: the very first question of a session
        # always misses this way (nothing was ever drafted early enough to
        # prime from), and it is not the only case -- any question sent
        # quickly after its draft settles can too.
        self.preparing: Optional["asyncio.Task"] = None
        # The in-flight background re-prime task, if one is running right now
        # -- set by _reprime_after_reply at dispatch, cleared when it finishes
        # (only by itself, same stale-clear guard as `preparing`).
        #
        # Exists so a real question that arrives WHILE the previous answer is
        # still being re-read can cancel that read instead of contending with
        # it: re-prime and the new question's own prefill both want gemma2 on
        # the same 2 cores, and once the question has arrived, re-prime's
        # result is moot anyway -- the question is about to read that exact
        # prefix itself.
        self.repriming: Optional["asyncio.Task"] = None
        # The system prompt (persona) sent on the MOST RECENT real LLM call,
        # verbatim -- compared against the next turn's to log whether Ollama's
        # KV cache prefix actually held (byte-identical -> cached) or forked
        # (changed -> full re-prefill). It should never change within a
        # session in the normal case (build_system_prompt is a pure function
        # of `profile` and the pinned block, both fixed once a session
        # starts) -- this exists to CATCH it when it does, e.g. get_or_create
        # overwriting `profile` on an existing session, rather than assume.
        self.last_system_prompt: Optional[str] = None

    def remember_chunks(self, chunk_ids: List[int]) -> List[int]:
        """Add newly retrieved chunk ids, preserving order and skipping repeats.

        Returns the full accumulated list. Order is append-only on purpose --
        re-sorting by relevance would rewrite the prefix and cost exactly what
        this exists to avoid.
        """
        known = set(self.context_chunk_ids)
        for cid in chunk_ids:
            if cid not in known:
                self.context_chunk_ids.append(cid)
                known.add(cid)
        return self.context_chunk_ids

    def claim_prepared(self, chunk_ids: List[int]) -> Optional[PreparedPassage]:
        """Take the prepared passage if it is still usable for this exact
        retrieval, clearing it either way -- a rejected guess is not saved for
        a later question, because the next question is a different guess.

        Usable means BOTH: the real question retrieved the same passages (in
        the same order -- a different order is a different ranking, not the
        same answer), and nothing has been added to this session's history
        since the prime was built. The second check matters even when the
        first passes: a prime built one question ago has the wrong prefix
        now, and reusing it would hand Ollama a prompt it has no cache for.
        """
        prepared, self.prepared = self.prepared, None
        if prepared is None:
            return None
        if prepared.chunk_ids != chunk_ids:
            return None
        if prepared.history_len != len(self.messages):
            return None
        return prepared

    def add(self, role: str, content: str) -> Message:
        message = Message(role=role, content=content, created_at=_now())
        self.messages.append(message)
        self.updated_at = message.created_at
        return message

    def pop_last(self, count: int = 1) -> None:
        """Undo the most recent `count` messages.

        Used to roll back the student's turn when generation fails, so a retry
        does not leave a partial turn in the history. `count` is more than 1
        for an early-primed turn: it added a passage and an acknowledgement
        ahead of the question, and popping only the question would leave that
        acknowledgement dangling with nothing after it -- a shape no real turn
        ever produces and later replay has no way to make sense of.
        """
        for _ in range(max(0, count)):
            if not self.messages:
                break
            self.messages.pop()
        self.updated_at = self.messages[-1].created_at if self.messages else self.created_at

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
