"""Request/response models.

These double as the API contract: FastAPI renders them into the OpenAPI schema
served at /docs, so the frontend can generate types straight from /openapi.json.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

try:  # Literal lives in typing from 3.8, kept explicit for clarity
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal  # type: ignore

Role = Literal["system", "user", "assistant"]
TeachingStyle = Literal["teach", "socratic", "direct", "exam_prep"]
Difficulty = Literal["easy", "medium", "hard"]


# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------
class Message(BaseModel):
    role: Role
    content: str
    created_at: Optional[datetime] = None


class Usage(BaseModel):
    """Local-inference stats. Handy for showing 'runs offline, this fast' in a demo."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_duration_ms: int = 0
    load_duration_ms: int = 0
    tokens_per_second: float = 0.0
    # The prefill/decode split, which `total_duration_ms` hides. On CPU these
    # respond to opposite levers: prefill scales with how much context was
    # pasted in (so with rag_top_k and chunk size), decode with max_tokens and
    # how verbose the persona is. One aggregate number cannot tell you which
    # one a change moved.
    prompt_eval_ms: int = 0
    eval_ms: int = 0


class TutorProfile(BaseModel):
    """Who the tutor is talking to. Persisted on the session."""

    subject: Optional[str] = Field(None, examples=["Biology"])
    level: Optional[str] = Field(None, examples=["Grade 8"])
    style: TeachingStyle = "teach"
    language: str = "English"
    student_name: Optional[str] = None


class GenerationOptions(BaseModel):
    """Per-request overrides; all optional, all fall back to settings."""

    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=4096)


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------
class ChatRequest(GenerationOptions):
    message: str = Field(..., min_length=1, examples=["Why is the sky blue?"])
    session_id: Optional[str] = Field(
        None, description="Omit to start a new conversation; the id is returned."
    )
    profile: Optional[TutorProfile] = Field(
        None, description="Applied when creating a session; updates it if supplied later."
    )


class Source(BaseModel):
    """A textbook passage the reply was grounded in."""

    title: str
    heading: str = ""
    page_start: int
    page_end: int
    grade: Optional[int] = None
    subject: Optional[str] = None
    distance: float = 0.0


class RetrievalMetrics(BaseModel):
    """How retrieval behaved on one question.

    Reference-free: none of this is a correctness measurement, because there is
    no golden answer at query time. `scripts/evaluate_retrieval.py` against the
    golden set is still the only thing that measures recall. These are the
    proxies that move with it, reported per turn so a regression is visible
    before anyone reruns the harness.
    """

    query_language: str = ""
    # The distance ceiling that applied, which is per query language -- a hit
    # at 0.55 is a good English result rejected and a fine Hindi one accepted.
    ceiling: float = 0.0
    grade: Optional[int] = None
    lexical_query: bool = False

    embed_ms: float = 0.0
    dense_ms: float = 0.0
    lexical_ms: float = 0.0
    total_ms: float = 0.0

    # The funnel. Where candidates are lost says which knob to reach for.
    candidates: int = 0
    dense_hits: int = 0
    gate_survivors: int = 0
    lexical_hits: int = 0
    lexical_eligible: int = 0
    fused: int = 0
    returned: int = 0
    dropped_over_budget: int = 0

    best_distance: Optional[float] = None
    # ceiling - best_distance. Near zero means this answer only just cleared.
    headroom: Optional[float] = None
    # Gap from the best dense hit to the runner-up; a flat cluster means the
    # ranking between them is close to arbitrary.
    separation: Optional[float] = None
    both_legs: int = 0

    context_tokens: int = 0
    context_budget: int = 0

    abstained: bool = True
    abstain_reason: str = ""


class TurnMetrics(BaseModel):
    """What one answer cost, end to end.

    Wall clock measured on the server, except the three Ollama counters, which
    are what the model itself reports. Both are kept: Ollama's numbers say what
    the model spent, the wall clock says what the student waited, and
    `overhead_ms` is the gap between them.
    """

    retrieval: RetrievalMetrics = Field(default_factory=RetrievalMetrics)

    retrieval_ms: float = 0.0
    # Server-side time to first token, and the number that decides whether the
    # tutor feels responsive -- the rest decodes while the first sentence is
    # already being spoken. Null on the buffered endpoint, which has no first
    # token to time.
    ttft_ms: Optional[float] = None
    llm_ms: float = 0.0
    # A socratic reply that lectured is re-asked once: a second full
    # generation, invisible in either call's own counters.
    retry_ms: float = 0.0
    total_ms: float = 0.0

    load_ms: int = 0
    prefill_ms: int = 0
    decode_ms: int = 0
    overhead_ms: float = 0.0

    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_per_second: float = 0.0

    # Overlap between the answer's wording and the passages cited under it.
    # Null whenever it could not be measured -- an unaided answer is not an
    # ungrounded one, and neither is a Hindi answer written from an English
    # page. `groundedness_note` says which, and is "" when a score is present.
    groundedness: Optional[float] = None
    groundedness_note: str = ""


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    model: str
    usage: Usage
    created_at: datetime
    # Empty whenever the library is absent or nothing matched, which is also
    # how the UI knows an answer came from the model alone.
    sources: List[Source] = Field(default_factory=list)
    metrics: Optional[TurnMetrics] = None


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------
class SessionCreateRequest(BaseModel):
    profile: Optional[TutorProfile] = None


class SessionSummary(BaseModel):
    session_id: str
    profile: TutorProfile
    message_count: int
    created_at: datetime
    updated_at: datetime
    preview: Optional[str] = None


class SessionDetail(SessionSummary):
    messages: List[Message]


class DeleteResponse(BaseModel):
    session_id: str
    deleted: bool


# --------------------------------------------------------------------------
# Tutor: explain
# --------------------------------------------------------------------------
class ExplainRequest(GenerationOptions):
    topic: str = Field(..., min_length=1, examples=["Photosynthesis"])
    level: str = Field("beginner", examples=["Grade 8"])
    language: str = "English"


class ExplainResponse(BaseModel):
    topic: str
    level: str
    summary: str
    key_points: List[str]
    analogy: str
    check_question: str
    model: str
    usage: Usage


# --------------------------------------------------------------------------
# Tutor: quiz
# --------------------------------------------------------------------------
class QuizRequest(GenerationOptions):
    topic: str = Field(..., min_length=1, examples=["The water cycle"])
    num_questions: int = Field(3, ge=1, le=10)
    num_options: int = Field(4, ge=2, le=6)
    difficulty: Difficulty = "medium"
    level: str = Field("beginner", examples=["Grade 8"])


class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    answer_index: int
    explanation: str


class QuizResponse(BaseModel):
    topic: str
    difficulty: Difficulty
    questions: List[QuizQuestion]
    model: str
    usage: Usage


# --------------------------------------------------------------------------
# Tutor: evaluate a student's answer
# --------------------------------------------------------------------------
class EvaluateRequest(GenerationOptions):
    question: str = Field(..., min_length=1)
    student_answer: str = Field(..., min_length=1)
    expected_answer: Optional[str] = None
    level: str = "beginner"


class EvaluateResponse(BaseModel):
    verdict: Literal["correct", "partially_correct", "incorrect"]
    score: int = Field(..., ge=0, le=100)
    feedback: str
    hint: str
    model: str
    usage: Usage


# --------------------------------------------------------------------------
# Health & models
# --------------------------------------------------------------------------
class OllamaStatus(BaseModel):
    reachable: bool
    host: str
    version: Optional[str] = None
    error: Optional[str] = None


class ModelStatus(BaseModel):
    name: str
    available: bool
    available_models: List[str] = []


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app: str
    version: str
    offline: bool = Field(True, description="Inference is local; no internet required.")
    ollama: OllamaStatus
    model: ModelStatus
    active_sessions: int
    # Free-form: the shape differs between "available" and "why it isn't".
    library: Dict[str, Any] = Field(default_factory=dict)


class ModelInfo(BaseModel):
    name: str
    size_bytes: Optional[int] = None
    parameter_size: Optional[str] = None
    quantization: Optional[str] = None
    family: Optional[str] = None
    modified_at: Optional[str] = None


class ModelListResponse(BaseModel):
    default_model: str
    models: List[ModelInfo]


class ErrorResponse(BaseModel):
    detail: str
    hint: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
