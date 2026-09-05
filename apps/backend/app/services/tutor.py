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
    # The default. A small model left alone answers school questions with a
    # vague one-liner; this forces a real (but short) explanation with an
    # example — it's a voice tutor, so keep it tight.
    "teach": (
        "Answer in 2-3 short sentences: say what the concept is in plain words, "
        "then give one concrete everyday example a school student would "
        "recognise. Use simple language. Do not add a question at the end unless "
        "it genuinely helps. Never reply with only a vague one-line definition, "
        "and never pad it out past three sentences."
    ),
    # Abstract phrasing like "guide with questions" is ignored by small models;
    # a hard length limit plus a worked example is what actually lands.
    "socratic": (
        "Give a short, correct answer to what was asked (1-2 sentences), then "
        "end with exactly ONE short question that nudges the student one step "
        "further. Your reply MUST end with that question mark. Never offer a "
        "menu of options ('do you want A or B?'); ask one focused question. "
        "Do not pad with encouragement or emoji."
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
        "You are a patient tutor for a school student who is learning a topic "
        "and preparing for exams. Explain every concept clearly enough that the "
        "student can understand it and use it, and include a concrete example. "
        "Never answer with just a vague one-line definition. Always answer the "
        "question the student actually asked, on its own terms — do not force it "
        "into a preset subject.",
    ]
    if profile.subject:
        lines.append(
            "Today's focus is {}, but still answer other questions directly.".format(
                profile.subject
            )
        )
    if profile.level:
        lines.append(
            "Pitch the explanation so a {} student can follow it — plain wording, "
            "but keep the real substance; do not oversimplify into baby talk.".format(
                profile.level
            )
        )
    if profile.student_name:
        lines.append("The student's name is {}.".format(profile.student_name))

    language = profile.language or "English"
    # Hindi and Marathi are both written in Devanagari; naming the script beats
    # "the <language> script", which a small model reads loosely.
    script = {"hindi": "Devanagari", "marathi": "Devanagari"}.get(
        language.strip().lower()
    )
    lines.extend(
        [
            "Keep answers under 80 words unless asked for more.",
            "Use simple language and a concrete example. Never invent facts; if "
            "you are unsure, say so plainly.",
            "Write plain prose only: full sentences in one short paragraph. No "
            "markdown, no bullet points, no numbered or lettered lists, no "
            "headings, no bold text or asterisks, and never use emojis, "
            "emoticons, or decorative symbols.",
            "You are the tutor speaking straight to the student. Never say you "
            "are an AI, never talk about your limitations, and never refuse. If "
            "the question is garbled or unclear, answer the most likely intended "
            "question instead of asking what they meant.",
            "Reply in {}.".format(language),
        ]
    )
    # Trailing position is deliberate: a small model follows the last
    # instruction most closely, and mid-prompt style rules got ignored.
    lines.append("Most important rule: " + STYLE_RULES.get(profile.style, STYLE_RULES["teach"]))

    # ...but "reply in <language>" then loses to that last line, so for a
    # non-English language repeat it *after* it, as hard as possible — small
    # models otherwise drift straight back to English.
    if language.strip().lower() != "english":
        script_clause = (
            "using the {} script".format(script)
            if script
            else "using the native {} script".format(language)
        )
        lines.append(
            "Write your ENTIRE reply in {0}, and only {0}, {1}. Every sentence "
            "must be in {0}. Do not use English or any other script. Do not use "
            "emojis or emoticons. Do NOT repeat a word or phrase — make each "
            "point once, then stop.".format(language, script_clause)
        )
        # A short worked example in the target script shows the expected shape —
        # a plain definition plus one example, then stop.
        if script == "Devanagari":
            lines.append(
                "उदाहरण — छात्र: \"संज्ञा क्या होती है?\" "
                "उत्तर: \"किसी व्यक्ति, वस्तु, स्थान या भाव के नाम को संज्ञा कहते हैं। "
                "जैसे वाक्य 'राम दिल्ली में रहता है' में 'राम' और 'दिल्ली' दोनों संज्ञा हैं, "
                "क्योंकि एक व्यक्ति का नाम है और दूसरा स्थान का।\""
            )

    prompt = " ".join(lines)
    if context:
        # Appended after the rules rather than before them. This model weights
        # the end of the prompt most heavily, and a few hundred words of
        # textbook dropped in front of the persona pushed the style rules out
        # of reach -- it started reciting the passage instead of tutoring from
        # it. The rules -- and, for a non-English turn, the script instruction
        # that has to survive to the very end -- stay adjacent to the reply;
        # the excerpts sit above.
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
