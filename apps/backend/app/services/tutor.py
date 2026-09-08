"""Tutor prompts and structured-output schemas.

Prompt notes for a 1.5B model: keep instructions short, concrete and numbered.
Long persona essays make small models drift, and constraining the decoder with
a JSON schema is far more reliable than asking politely for JSON.
"""

import json
import re
from typing import Any, Dict, List, Optional

from app.schemas import TutorProfile

STYLE_RULES = {
    # Abstract phrasing like "guide with questions" is ignored by small models;
    # a hard length limit plus a worked example is what actually lands.
    "socratic": (
        "Do NOT explain the whole concept at once. Reply in at most 3 "
        "sentences: give one small hint, then end with a question that makes "
        "the student think. Your reply MUST end with a question mark. Give the "
        "full answer only if the student asks for it directly."
    ),
    "direct": (
        "Answer clearly and immediately, then add one short worked example."
    ),
    "exam_prep": (
        "Be concise and exam-focused. Give the answer, the marking points, and "
        "one common mistake to avoid."
    ),
}


def build_system_prompt(
    profile: Optional[TutorProfile], context: Optional[str] = None
) -> str:
    profile = profile or TutorProfile()
    lines: List[str] = [
        "You are a patient, encouraging tutor running entirely offline on the "
        "student's own device.",
    ]
    if profile.subject:
        lines.append("Subject: {}.".format(profile.subject))
    if profile.level:
        lines.append("The student's level is: {}. Match your vocabulary to it.".format(profile.level))
    if profile.student_name:
        lines.append("The student's name is {}.".format(profile.student_name))

    lines.extend(
        [
            "Keep answers under 200 words unless asked for more.",
            "Use simple language and a concrete example. Never invent facts; if "
            "you are unsure, say so plainly.",
            "Reply in {}.".format(profile.language or "English"),
        ]
    )
    # Trailing position is deliberate: a 1.5B model follows the last
    # instruction most closely, and mid-prompt style rules got ignored.
    lines.append("Most important rule: " + STYLE_RULES.get(profile.style, STYLE_RULES["socratic"]))
    prompt = " ".join(lines)
    if context:
        # Appended after the rules rather than before them. This model weights
        # the end of the prompt most heavily, and a few hundred words of
        # textbook dropped in front of the persona pushed the style rules out
        # of reach -- it started reciting the passage instead of tutoring from
        # it. The rules stay adjacent to the reply; the excerpts sit above.
        #
        # It is tempting to move the excerpts out of this message entirely and
        # attach them to the question instead: they are the only part of the
        # prompt that changes each turn, so parking them in messages[0] means
        # Ollama's KV cache is invalidated from token zero and the persona and
        # the whole conversation are re-read every single turn. That was tried
        # and measured, and it is not worth it. Against 12 pronoun follow-ups
        # ("why does it get bigger?", "can I make one at home?") over three
        # topics, keeping the excerpts here answered from the conversation
        # 11/12 times; moving them next to the question dropped that to 5/12,
        # and 7/12 even with the style rule restated below them. With the
        # excerpts adjacent to the reply, an irrelevant retrieval hit -- which
        # a pronoun-only follow-up reliably produces, since the question alone
        # embeds to nothing useful -- simply overrides the conversation, and
        # the tutor starts answering about hens and cows. Front placement keeps
        # them subordinate to the dialogue.
        #
        # The cache would have been worth ~140 tokens a turn, about 3s on the
        # target laptop. Cutting MAX_HISTORY_MESSAGES and RAG_CONTEXT_MAX_CHARS
        # buys four times that without touching answer quality. Fix the
        # retrieval instead if this needs revisiting: the follow-ups above came
        # back at distance 0.35-0.40, just inside RAG_MAX_DISTANCE.
        prompt = "{}\n\n{}".format(context, prompt)
    return prompt


def grade_from_profile(profile: Optional[TutorProfile]) -> Optional[int]:
    """Pull an integer grade out of the free-text level on the profile.

    The profile carries level as prose ("Grade 8", "Class 6"), because that is
    what the prompt wants, but retrieval partitions on an integer. Anything
    unparseable returns None, which searches every grade rather than guessing
    one -- a wrong grade silently hides the right chapter.
    """
    if profile is None or not profile.level:
        return None
    match = re.search(r"\d{1,2}", profile.level)
    if not match:
        return None
    grade = int(match.group())
    return grade if 1 <= grade <= 12 else None




def build_chat_messages(
    history: List[Dict[str, str]],
    profile: Optional[TutorProfile],
    context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Prepend the persona (and any retrieved textbook context) to the history."""
    return [
        {"role": "system", "content": build_system_prompt(profile, context)}
    ] + history


# --------------------------------------------------------------------------
# Structured tasks
# --------------------------------------------------------------------------
EXPLAIN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 5,
        },
        "analogy": {"type": "string"},
        "check_question": {"type": "string"},
    },
    "required": ["summary", "key_points", "analogy", "check_question"],
}


def explain_messages(topic: str, level: str, language: str) -> List[Dict[str, str]]:
    system = (
        "You are a tutor explaining a topic to a {} student. Reply in {}. "
        "Use plain language, no markdown, and no letter prefixes."
    ).format(level, language)
    user = (
        "Explain: {topic}\n"
        "Return:\n"
        "1. summary: 2-3 sentences a {level} student understands.\n"
        "2. key_points: 3 to 5 short bullet facts.\n"
        "3. analogy: one everyday comparison.\n"
        "4. check_question: one question to test understanding."
    ).format(topic=topic, level=level)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def quiz_schema(num_questions: int, num_options: int) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "minItems": num_questions,
                "maxItems": num_questions,
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": num_options,
                            "maxItems": num_options,
                        },
                        # The model states the correct option verbatim; the
                        # server derives the index. Small models reliably name
                        # the right option but miscount its position.
                        "answer": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["question", "options", "answer", "explanation"],
                },
            }
        },
        "required": ["questions"],
    }


def quiz_messages(
    topic: str, num_questions: int, num_options: int, difficulty: str, level: str
) -> List[Dict[str, str]]:
    system = (
        "You write multiple-choice quiz questions for a {} student. "
        "Exactly one option is correct. Do not prefix options with letters or "
        "numbers. Copy the correct option into `answer` word for word, exactly "
        "as it appears in `options`."
    ).format(level)
    user = (
        "Topic: {topic}\n"
        "Write {n} {difficulty} multiple-choice questions with exactly {k} "
        "options each. Every question must be answerable from the topic alone. "
        "Add a one-sentence explanation of why the correct option is right."
    ).format(topic=topic, n=num_questions, difficulty=difficulty, k=num_options)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


EVALUATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        # Decoded first, on purpose: the model decides the one factual question
        # before it has to name a verdict. Internal only -- not returned by the API.
        "is_anything_wrong": {"type": "boolean"},
        "verdict": {
            "type": "string",
            "enum": ["correct", "partially_correct", "incorrect"],
        },
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "feedback": {"type": "string"},
        "hint": {"type": "string"},
    },
    "required": ["is_anything_wrong", "verdict", "score", "feedback", "hint"],
}


def evaluate_messages(
    question: str, student_answer: str, expected_answer: Optional[str], level: str
) -> List[Dict[str, str]]:
    # Kept deliberately short. A longer rubric made the model default every
    # answer to the middle band, including fully correct ones.
    system = (
        "Grade a {} student's answer.\n"
        "is_anything_wrong: true if the student said anything factually false.\n"
        "If is_anything_wrong is true -> verdict 'incorrect', score below 40.\n"
        "Else if the key idea is there -> 'correct', score 85-100.\n"
        "Else -> 'partially_correct', score 40-84.\n"
        "Never agree with a false statement."
    ).format(level)

    parts = ["Question: {}".format(question), "Student answer: {}".format(student_answer)]
    if expected_answer:
        parts.append("Reference answer: {}".format(expected_answer))
    # Reverted to a bare instruction: adding a second-person rule here cost
    # grading accuracy (5/6 -> 4/6 verdicts) without fixing the phrasing. On a
    # 1.5B model, every extra instruction is paid for somewhere else.
    parts.append("Grade the student answer.")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(parts)},
    ]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
def parse_json_content(content: str) -> Dict[str, Any]:
    """Parse a model's JSON reply, tolerating code fences and stray prose.

    Schema-constrained decoding makes this rare, but a POC should not 500
    because a small model emitted a stray ``` fence.
    """
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1] if len(text.split("```")) > 1 else text
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError("Model did not return valid JSON: {}".format(text[:300]))


# --------------------------------------------------------------------------
# Socratic self-correction
# --------------------------------------------------------------------------
# qwen2.5:1.5b follows a socratic instruction roughly a quarter of the time, no
# matter how the persona is phrased (rule-only, rule-last, one example, two
# examples and few-shot turns were all measured). Rather than trust the prompt,
# the reply is checked and re-asked once. One extra short generation costs ~1s.
SOCRATIC_CORRECTION = (
    "That reply explained too much. My question was: \"{question}\". Rewrite "
    "your reply in at most 2 sentences, strictly about that question: one small "
    "hint, then ONE question back to me. Your whole reply must end with a "
    "question mark. Do not give the answer. Do not change the subject."
)


def needs_socratic_retry(reply: str, profile: Optional[TutorProfile]) -> bool:
    """True when socratic mode was requested but the model lectured instead."""
    if profile is None or profile.style != "socratic":
        return False
    return not reply.strip().endswith("?")


def socratic_retry_messages(
    base_messages: List[Dict[str, str]], reply: str, question: str
) -> List[Dict[str, str]]:
    """Original turns + the offending reply + a topic-anchored correction."""
    return base_messages + [
        {"role": "assistant", "content": reply},
        {"role": "user", "content": SOCRATIC_CORRECTION.format(question=question)},
    ]
