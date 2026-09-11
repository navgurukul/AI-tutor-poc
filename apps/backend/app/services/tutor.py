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
    # a concrete shape plus a sentence count is what actually lands.
    #
    # Tuned twice against measured answer length on the target laptop, and it
    # overshoots easily in both directions:
    #
    #   "at most 3-5 sentences - one small hint"        -> 223 chars, too curt
    #   "4 to 6 sentences: key idea, example, nudge"    -> 851 chars, too long
    #   this rule                                       -> targeting ~450
    #
    # Naming the three parts is what lifts the length, and it lifts it hard --
    # far more than the sentence count restrains it. So the count comes down
    # and a word cap goes in as a hard anchor, because "3 to 4 sentences" alone
    # licenses three very long ones.
    #
    # Naming them also gets them echoed. Written as "...: the key idea, one
    # concrete example, then one line that nudges them to think", the model read
    # the colon-list as a template and emitted "Key points:" and "Nudge them"
    # as literal headings in the reply. Two fixes, both needed: the shape is
    # prose rather than a list, and the label words the model was copying
    # ("key idea", "nudges") are gone. The ban on headings is explicit because
    # a 1.5B model will reintroduce structure from almost any enumerated
    # instruction.
    #
    # Length is not free even though the student is reading rather than
    # waiting: the closing line comes back through the history window on the
    # next turn (see Session.history), and generation runs at ~15.6 tokens/s.
    #
    # No question-mark requirement. It used to end "your reply MUST end with a
    # question mark", which the model obeyed to the letter and made every
    # answer read as interrogation. needs_socratic_retry below changed with it.
    "socratic": (
        "answer in 3 to 4 plain sentences, under 80 words. Start with the main "
        "idea, then give one example a student can picture, then end by "
        "inviting them to think further. Write flowing sentences only -- no "
        "headings, labels, bullet points or numbered parts. Do not explain the "
        "whole topic at once."
    ),
    "direct": (
        "Answer clearly and immediately, then add one short worked example."
    ),
    "exam_prep": (
        "Be concise and exam-focused. Give the answer, the marking points, and "
        "one common mistake to avoid."
    ),
}

# Sits between the persona and the excerpts, so the model reads what the
# passages are for before it reads the passages. Deliberately permissive: a
# 1.5B model told to answer *only* from context refuses far too often, which
# reads to a student as the tutor being broken.
EXCERPT_PREAMBLE = (
    "Use the student's textbook excerpts when relevant, prioritizing their "
    "wording and examples over your own knowledge."
)


def build_system_prompt(
    profile: Optional[TutorProfile], context: Optional[str] = None
) -> str:
    """Persona and style rule, then the excerpt preamble, then the excerpts.

    The conversation is not part of this message -- it follows as its own turns
    (see build_chat_messages), so the excerpts stay subordinate to the dialogue
    rather than sitting next to the question.

    This ordering replaced the previous one, which put the excerpts at the very
    top, above the persona. That arrangement was chosen because the model
    weights the end of the prompt most heavily and a few hundred words of
    textbook in front of the persona pushed the style rules out of reach -- it
    recited the passage instead of tutoring from it. The style rule is now
    shorter and the preamble frames the excerpts explicitly, which is what
    makes the flip viable; the drift it was guarding against is worth
    re-checking on a real book if answers start reading like recitation.

    What was measured before the flip, and still holds: excerpts must not move
    out of this message and onto the question. Against 12 pronoun follow-ups
    ("why does it get bigger?", "can I make one at home?") over three topics,
    excerpts in the system message answered from the conversation 11/12 times;
    attached to the question, 5/12, and 7/12 even with the style rule restated
    below them. A pronoun-only follow-up embeds to nothing useful, so retrieval
    returns weakly related chunks just inside RAG_MAX_DISTANCE (0.35-0.40);
    adjacent to the question they override the dialogue and the tutor starts
    answering about hens and cows.

    One incidental gain: the persona and preamble are now a fixed prefix, so
    Ollama's KV cache survives them instead of being invalidated at token zero
    by excerpts that change every turn. It is a small prefix, so expect a small
    win -- RAG_CONTEXT_MAX_CHARS is the lever that still moves a turn.
    """
    profile = profile or TutorProfile()
    persona = "Patient tutor"
    if profile.level:
        persona += " for a {} student".format(profile.level)
    lines: List[str] = [persona + "."]
    if profile.subject:
        lines.append("Subject: {}.".format(profile.subject))
    if profile.student_name:
        lines.append("The student's name is {}.".format(profile.student_name))
    lines.append(
        "Simple words, {}, never invent facts.".format(profile.language or "English")
    )
    lines.append(
        "Most important rule: "
        + STYLE_RULES.get(profile.style, STYLE_RULES["socratic"])
    )
    prompt = " ".join(lines)
    if context:
        prompt = "{}\n\n{}\n\n{}".format(prompt, EXCERPT_PREAMBLE, context)
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
#
# Only /api/chat reaches this; /api/chat/stream cannot, because the reply is
# already on the student's screen token by token before there is anything to
# inspect. The UI streams, so in practice this guards the buffered API only.
SOCRATIC_CORRECTION = (
    "That reply explained too much. My question was: \"{question}\". Rewrite it "
    "in 4 sentences or fewer, strictly about that question: the key idea, one "
    "example, and a nudge to think further. Do not walk through the whole "
    "topic. Do not change the subject."
)

# Roughly twice what the style rule asks for. A well-shaped 6-sentence reply
# runs 400-600 characters on this model; the failure being caught is the
# wholesale topic dump, which runs well past this. Deliberately set clear of
# the target rather than at it: a retry costs a second full generation, so a
# merely wordy answer must never trigger one.
SOCRATIC_MAX_CHARS = 1200


def needs_socratic_retry(reply: str, profile: Optional[TutorProfile]) -> bool:
    """True when socratic mode was requested but the model lectured instead.

    This was a question-mark test, back when the style rule ended "your reply
    MUST end with a question mark". The rule no longer asks for one, so that
    test would now fire on nearly every reply and buy a wasted second
    generation on every buffered call. Length is the signal that survives the
    rule change: what the rule actually forbids is explaining the whole topic
    at once, and that failure is visible in the character count.
    """
    if profile is None or profile.style != "socratic":
        return False
    return len(reply.strip()) > SOCRATIC_MAX_CHARS


def socratic_retry_messages(
    base_messages: List[Dict[str, str]], reply: str, question: str
) -> List[Dict[str, str]]:
    """Original turns + the offending reply + a topic-anchored correction."""
    return base_messages + [
        {"role": "assistant", "content": reply},
        {"role": "user", "content": SOCRATIC_CORRECTION.format(question=question)},
    ]
