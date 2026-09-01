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


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    model: str
    usage: Usage
    created_at: datetime


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
