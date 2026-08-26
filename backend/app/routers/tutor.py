"""Structured tutor tasks: explain, quiz, evaluate.

Each one constrains Ollama's decoder with a JSON schema, so the frontend gets a
predictable object to render instead of prose it has to parse.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from app.schemas import (
    EvaluateRequest,
    EvaluateResponse,
    ExplainRequest,
    ExplainResponse,
    QuizQuestion,
    QuizRequest,
    QuizResponse,
    Usage,
)
from app.services.ollama_client import build_usage, client
from app.services.tutor import (
    EVALUATE_SCHEMA,
    EXPLAIN_SCHEMA,
    evaluate_messages,
    explain_messages,
    parse_json_content,
    quiz_messages,
    quiz_schema,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tutor", tags=["tutor"])


def _resolve_answer_index(answer: Optional[str], options: List[str]) -> int:
    """Map the model's stated answer text onto its position in `options`.

    The model names the correct option accurately but miscounts its index
    (it tends to answer 1-based), so the index is derived here instead.
    Matching is exact-insensitive first, then a containment fallback for when
    the model paraphrases slightly.
    """
    if not answer:
        return 0
    target = answer.strip().lower()
    normalised = [o.strip().lower() for o in options]
    if target in normalised:
        return normalised.index(target)
    for i, option in enumerate(normalised):
        if option and (option in target or target in option):
            return i
    return 0


def _parse_or_502(response, what: str):
    content = (response.get("message") or {}).get("content", "")
    try:
        return parse_json_content(content)
    except ValueError as exc:
        logger.warning("Malformed %s payload: %s", what, content[:300])
        raise HTTPException(
            status_code=502,
            detail="The model returned malformed {} data. Try again -- small "
            "models occasionally produce invalid output. ({})".format(what, exc),
        )


@router.post("/explain", response_model=ExplainResponse, summary="Explain a topic")
async def explain(request: ExplainRequest) -> ExplainResponse:
    """A structured explainer card: summary, key points, an analogy, and a
    comprehension question."""
    response = await client.chat(
        explain_messages(request.topic, request.level, request.language),
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens or 700,
        response_format=EXPLAIN_SCHEMA,
    )
    data = _parse_or_502(response, "explanation")
    return ExplainResponse(
        topic=request.topic,
        level=request.level,
        summary=data.get("summary", ""),
        key_points=data.get("key_points", []),
        analogy=data.get("analogy", ""),
        check_question=data.get("check_question", ""),
        model=response.get("model", ""),
        usage=Usage(**build_usage(response)),
    )


@router.post("/quiz", response_model=QuizResponse, summary="Generate a quiz")
async def quiz(request: QuizRequest) -> QuizResponse:
    """Multiple-choice questions with a 0-based `answer_index` and an explanation."""
    # Roughly 120 tokens per question, plus headroom for the JSON scaffolding.
    budget = request.max_tokens or min(4096, 200 + request.num_questions * 160)
    response = await client.chat(
        quiz_messages(
            request.topic,
            request.num_questions,
            request.num_options,
            request.difficulty,
            request.level,
        ),
        model=request.model,
        temperature=request.temperature if request.temperature is not None else 0.5,
        max_tokens=budget,
        response_format=quiz_schema(request.num_questions, request.num_options),
    )
    data = _parse_or_502(response, "quiz")

    questions = []
    for item in data.get("questions", []):
        options = item.get("options") or []
        if not options:
            continue
        questions.append(
            QuizQuestion(
                question=item.get("question", ""),
                options=options,
                answer_index=_resolve_answer_index(item.get("answer"), options),
                explanation=item.get("explanation", ""),
            )
        )
    if not questions:
        raise HTTPException(status_code=502, detail="The model returned no questions.")

    return QuizResponse(
        topic=request.topic,
        difficulty=request.difficulty,
        questions=questions,
        model=response.get("model", ""),
        usage=Usage(**build_usage(response)),
    )


@router.post(
    "/evaluate", response_model=EvaluateResponse, summary="Grade a student answer"
)
async def evaluate(request: EvaluateRequest) -> EvaluateResponse:
    """Returns a verdict, a 0-100 score, feedback and a hint."""
    response = await client.chat(
        evaluate_messages(
            request.question, request.student_answer, request.expected_answer, request.level
        ),
        model=request.model,
        temperature=request.temperature if request.temperature is not None else 0.2,
        max_tokens=request.max_tokens or 400,
        response_format=EVALUATE_SCHEMA,
    )
    data = _parse_or_502(response, "evaluation")

    verdict = data.get("verdict", "partially_correct")
    if verdict not in ("correct", "partially_correct", "incorrect"):
        verdict = "partially_correct"
    score = data.get("score", 0)
    score = max(0, min(100, score)) if isinstance(score, int) else 0

    # The model settles the factual question before naming a verdict, but still
    # sometimes softens the verdict afterwards. Trust the boolean and keep the
    # score inside the band it implies.
    if data.get("is_anything_wrong") is True:
        verdict = "incorrect"
        score = min(score, 39)
    elif verdict == "correct":
        score = max(score, 85)

    return EvaluateResponse(
        verdict=verdict,
        score=score,
        feedback=data.get("feedback", ""),
        hint=data.get("hint", ""),
        model=response.get("model", ""),
        usage=Usage(**build_usage(response)),
    )
