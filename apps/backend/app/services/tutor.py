"""Tutor prompts and structured-output schemas.

Prompt notes for a 1.5B model: keep instructions short, concrete and numbered.
Long persona essays make small models drift, and constraining the decoder with
a JSON schema is far more reliable than asking politely for JSON.
"""

import json
import re
from typing import Any, Dict, List, Optional

from app.config import settings
from app.schemas import TutorProfile

# How to treat retrieved textbook excerpts. This used to be the first line of
# the context block itself, which put it *after* the persona and therefore in
# the half of the prompt that is re-prefilled every turn -- 61 tokens at ~36ms
# each, on every question, for a paragraph that never changes.
#
# It lives in the persona now, so it is inside the cached prefix and costs
# nothing after the warm-up. That is why it is phrased conditionally ("may be
# given"): it is emitted whether or not this particular turn retrieved
# anything, and a fixed string is the whole point -- make it vary with the
# turn and it stops being cacheable.
RETRIEVAL_RULE = (
    "You may be given excerpts from the student's own textbook. When they are "
    "provided, prefer them over your own knowledge where they apply, and use "
    "their wording and examples. If they do not cover the question, answer "
    "normally without mentioning them."
)

# The per-turn grounding nudge, attached (via build_turn_message's `grounded`
# flag) whenever this turn is answered from a passage -- inline in this turn
# or read into the conversation a turn earlier by early priming, either way.
#
# Wording history, both A/Bs on this box (see the fuller note beside its use):
#   2026-09-11, passage inline, 14 Q : "in your own words"     ground 0.179->0.266
#   2026-09-14, passage a turn back,  : "own wording" + example ground 0.326->0.390
#                8 Q, k=2 cap110        (vs no rule / a paraphrase-heavy one)
#
# "then add one everyday example" was UNCONDITIONAL until 2026-09-16, and that
# is very likely why: caught live, asked for a follow-up example on a passage
# about an ancient Ganga water-harvesting structure near Allahabad, the model
# invented a "गांधी बाँध" (garbling "गंगा" into a fabricated dam name) serving
# Delhi -- a city never mentioned in the source, and geographically wrong
# (Delhi is on the Yamuna). The source passage was correct; the model was
# just unconditionally told to produce an example whether or not the text
# actually supported one, so a 2B Q4_0 model under that instruction invented
# specifics rather than admitting the text didn't hand it one.
#
# Made conditional the same day, plus an explicit ban on invented specifics.
# NOT yet re-run through the 2026-09-14 groundedness A/B -- that measurement
# is for the unconditional wording and may not hold here; re-check before
# assuming this is free.
#
# The "copy proper names exactly" clause added the same day, separately: live,
# a passage that correctly said "चंबल बेसिन" (Chambal Basin) -- confirmed
# right there in the pasted text, not a corpus error -- came back from the
# model as "कंबल" (blanket). Not an invented fact (see the clause above,
# which guards against that); a smaller, quieter failure where the model has
# the right proper noun in its own context and still respells it. A likely
# real limit of a 2B, 4-bit-quantized model on less-common multi-syllable
# names, not something retrieval or wording can fully fix -- this is a
# mitigation, not a guaranteed correction.
GROUNDED_ANSWER_RULE = (
    "Answer using the facts in the text above, mainly in the text's own "
    "wording. If the text supports it, add one everyday example in one "
    "sentence -- but never invent a specific name, place, date, or number "
    "that is not in the text above. Copy any place, river, or proper name "
    "exactly as it is spelled in the text above."
)

STYLE_RULES = {
    # The default. A small model left alone answers school questions with a
    # vague one-liner; this forces a real (but short) explanation with an
    # example — it's a voice tutor, so keep it tight.
    # Lengthened 2026-09-10. At "2-3 short sentences" the model was landing on
    # 25-52 tokens -- roughly 15-25 Hindi words, well under even the 45-word
    # budget, and often a bare definition with nothing a student could learn
    # from. Three separate instructions were pushing it shorter (this rule, the
    # word budget, and the closing "one short paragraph"), and together they
    # overshot. Asking for four parts gives it something to fill rather than a
    # ceiling to duck under.
    #
    # Tried and REVERTED 2026-09-14: an instruction asking the model to open
    # with a short (<10 word) direct sentence, chasing time-to-first-audio.
    # Turned out to be solving an already-solved problem -- checked
    # useTutorSession.ts's drainSentences AFTER shipping this and found the
    # frontend already caps the OPENING spoken clip at 18-28 characters via
    # SPEECH_CLIP_RAMP, cutting on a clause boundary (comma/semicolon) or a
    # word boundary if the model's actual first sentence runs long. So
    # time-to-first-audio does not depend on how long the model's first
    # sentence is; the frontend already decouples the two. This instruction
    # only changed how every answer *opens* (a curt fact before elaborating)
    # for no measurable latency benefit, so it was pulled rather than kept on
    # an unverified guess -- see the frontend comment for the real mechanism
    # and rag_early_prime_wait_seconds' own history for why guessing without
    # measuring has cost real time this same day already.
    #
    # This costs decode time but NOT time-to-first-audio, for the reason above.
    "teach": (
        "Answer in 4-5 sentences: say what the concept is in plain words, then "
        "explain how or why it works, then give one concrete everyday example a "
        "school student would recognise, and finish with the one thing worth "
        "remembering. Use simple language. Do not add a question at the end "
        "unless it genuinely helps. Never reply with only a vague one-line "
        "definition."
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

    # Emitted whenever retrieval is switched on, not only when this turn found
    # something -- a rule that appears and disappears with the hit count would
    # change the prefix from turn to turn and lose the cache it was moved here
    # to win.
    if settings.rag_enabled:
        lines.append(RETRIEVAL_RULE)

    language = profile.language or "English"
    # Hindi and Marathi are both written in Devanagari; naming the script beats
    # "the <language> script", which a small model reads loosely.
    script = {"hindi": "Devanagari", "marathi": "Devanagari"}.get(
        language.strip().lower()
    )
    # A word budget is what the model can actually follow, but the hard cap it
    # has to finish inside (max_tokens) is counted in TOKENS -- and Devanagari
    # costs 2-4x more tokens per word than English. 80 words of Hindi is roughly
    # 160-320 tokens, so against the 120-token non-English cap the reply gets
    # guillotined mid-sentence. Budget each script to what its cap actually
    # holds, so the model lands the ending itself instead of being cut off.
    # Raised 45 -> 85 (Devanagari) and 70 -> 110 on 2026-09-10: answers were
    # coming back at 15-25 words, too thin to teach from. Devanagari stays lower
    # than English because it costs ~2 tokens per word against English's ~1.3,
    # so the same word count is a much bigger decode bill -- and the token caps
    # (max_tokens_non_english) were raised alongside so the cap still never
    # binds before the model finishes its own sentence.
    word_budget = 85 if script == "Devanagari" else 110
    lines.extend(
        [
            "Keep answers under {} words unless asked for more.".format(word_budget),
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
        # The "not a single Latin letter" clause is the one that stops a mixed-
        # script reply: gemma2:2b holds Devanagari for ordinary prose but drops
        # straight back to Latin for loanwords and acronyms ("AI क्या है" ->
        # "AI एक तकनीक है"). Naming the failure and showing the fix inline is
        # cheaper than a second worked example -- retrieved context is prepended
        # ahead of this persona, so the prefix is not cached and every extra
        # token here is paid again on every turn.
        # Shortened 2026-09-10, from a ~190-token block plus a worked example.
        #
        # It was that long because it was the LAST thing the model read, and it
        # had to carry the whole script instruction on its own. It no longer is:
        # build_turn_message ends every turn with "Reply only in <language>
        # (<script>)", which is where this model actually weights instructions. Keeping
        # the full version here as well was paying for the same rule twice.
        #
        # It is not free to keep. Prefill is ~4.2ms per prompt token even when
        # cached, so ~190 tokens of persona cost ~0.8s on EVERY turn. What stays
        # is the part the per-turn rule does not cover: how to handle loanwords
        # and acronyms, which is the specific failure ("AI क्या है" -> "AI एक
        # तकनीक है") that a bare "reply in Hindi" does not prevent.
        lines.append(
            "Write in {0} {1}. For technical terms and names use the everyday "
            "{0} word, or spell the term out in {2} ('AI' as 'ए॰आई॰'). No "
            "emojis. Do not repeat a phrase.".format(
                language, script_clause, script or language
            )
        )

    prompt = " ".join(lines)
    if context:
        # Order here is a straight trade between two measured effects, and they
        # pull in opposite directions.
        #
        # QUALITY wants the rules last. This model weights the end of the prompt
        # most heavily, and when a few hundred words of textbook sat between the
        # persona and the reply it started reciting the passage instead of
        # tutoring from it. That is why the excerpts used to go in front.
        #
        # LATENCY wants the persona first. Ollama reuses a cached KV prefix, and
        # the persona is byte-identical on every turn of a session while the
        # excerpts change with every question. With the excerpts in front there
        # is no reusable prefix at all, so the whole prompt is re-prefilled every
        # turn -- measured 2026-09-09 at ~36 ms/token, which made 869 prompt
        # tokens cost 31.6s before the student heard a single word.
        #
        # Both are satisfied by ordering it persona -> excerpts -> a SHORT
        # closing reminder, so the cacheable half leads and the rules are still
        # the last thing the model reads. The reminder is re-prefilled on every
        # turn, which is exactly why it is two sentences rather than a second
        # copy of the persona.
        closing = [
            "Answer the student's question using the excerpts above.",
            # The no-markdown rule is stated twice on purpose. It is already in
            # the persona, but the persona is now ~1300 tokens back behind the
            # whole pinned textbook, and this model weights the END of the
            # prompt -- which is the entire reason the style and script rules
            # were moved down here. Measured 2026-09-09: asked about संज्ञा the
            # model returned a markdown bulleted list ("* **व्यक्तिवाचक
            # संज्ञा:**") in flat defiance of the persona, and ran 141 tokens
            # against a 45-word budget. At 4.55 tok/s those extra ~90 tokens
            # cost roughly 20 SECONDS. Repeating one short sentence here is ~15
            # tokens of prefill at ~2.4ms each to save that.
            "Write plain sentences in one short paragraph — no bullet points, "
            "no asterisks, no bold, no headings.",
            "Keep it under {} words.".format(word_budget),
        ]
        if language.strip().lower() != "english":
            closing.append(
                "Write the entire reply in {}{} — not a single Latin letter.".format(
                    language, " using the {} script".format(script) if script else ""
                )
            )
        prompt = "{}\n\n{}\n\n{}".format(prompt, context, " ".join(closing))
    elif settings.tutor_rules_in_persona:
        # The reply rules, once, at the end of the persona -- which is cached, so
        # they cost nothing per turn -- instead of on every turn, where they were
        # the largest fixed part of each question's new tokens. The turn keeps a
        # short reminder (see build_turn_message). Only when nothing is pinned:
        # a pinned book already ends with its own closing rules.
        prompt = "{}\n\n{}".format(prompt, _persona_reply_rules(profile))
    return prompt


def _reply_rules(profile: Optional[TutorProfile]) -> List[str]:
    """The reply rules, as build_turn_message writes them for a turn with no excerpts.

    Kept in step with build_turn_message by tests/test_turn_rules.py.
    """
    profile = profile or TutorProfile()
    language = profile.language or "English"
    script = {"hindi": "Devanagari", "marathi": "Devanagari"}.get(language.strip().lower())
    word_budget = 85 if script == "Devanagari" else 110
    rules = [
        "Plain sentences, one paragraph, no bullets or bold.",
        "Under {} words.".format(word_budget),
        "Do not end with a question.",
    ]
    if language.strip().lower() != "english":
        rules.append("Reply only in {}{}.".format(language, " ({})".format(script) if script else ""))
    return rules


def _persona_reply_rules(profile: Optional[TutorProfile]) -> str:
    return (
        "Rules for every reply: " + " ".join(_reply_rules(profile)) + " " + GROUNDED_RULE_STANDING
    )


# The standing (persona-level) form of the grounding rule, phrased as a
# condition because -- unlike build_turn_message's per-turn `rules.insert(0,
# ...)`, which only runs when the caller already knows this turn is grounded
# -- the persona is written once and has to recognise a grounded turn for
# itself from inside the conversation.
#
# It used to recognise only "the message begins with textbook text", which
# matched every turn until early priming (2026-09-14) started sending the
# passage as its OWN earlier turn, closed by a fixed acknowledgement -- so the
# question turn no longer begins with textbook text at all, and this rule went
# silently dead for exactly the turns it most needed to cover. Kept as one
# shared standing rule covering both layouts rather than two, because a turn
# is either grounded or it isn't and the model does not need to know which
# shape produced that.
# Made conditional 2026-09-16, same day and same reason as GROUNDED_ANSWER_
# RULE's own note -- this is in fact the rule that produced the caught
# hallucination (a follow-up "give an example" reused the previous turn's
# passage, which this standing rule governs, not the per-turn one). The
# proper-name clause added the same day for the same reason as that rule's
# own copy -- see its comment for the caught चंबल -> कंबल case.
GROUNDED_RULE_STANDING = (
    "When the student's message begins with textbook text, or textbook facts "
    "were given in the turn just before it, answer using those facts, mainly "
    "in the text's own wording. If the text supports it, add one everyday "
    "example in one sentence -- but never invent a specific name, place, "
    "date, or number that is not in the text. Copy any place, river, or "
    "proper name exactly as it is spelled in the text. Never mention the "
    "text itself."
)


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




def build_turn_message(
    question: str,
    profile: Optional[TutorProfile],
    context: Optional[str] = None,
    *,
    grounded: Optional[bool] = None,
) -> str:
    """One student turn: its own excerpts, the question, then the rules.

    This is the shape the KV cache needs. Putting excerpts in the SYSTEM prompt
    seems tidier, but retrieval returns different passages for every question,
    so the system prompt changes every turn -- and because it sits at the front,
    changing it shifts the rules, the history and the question after it. That is
    a fork, and a fork reuses nothing. Measured 2026-09-10, same corpus, same
    question:

        excerpts grown in the system prompt : 27.7 ms/token on turn 2
        excerpts attached to the user turn  :  5.3 ms/token on turn 2

    Attached to the turn, the conversation only ever grows at the end: a
    follow-up that retrieves nothing new costs almost nothing, and a new topic
    costs only its own passages.

    The rules go AFTER the question rather than in the persona because this
    model weights the end of the prompt hardest -- the same reason they were
    moved out of the persona in the first place. With excerpts now inside the
    turn, the end of the prompt is here.

    `grounded` decides whether the textbook-answering rule (below) is attached.
    It defaults to `context is not None`, which is everything that shipped
    before 2026-09-14: the rule only ever made sense when a passage sat right
    above it. An early-primed turn (see rag.retrieval / chat.py's use of
    session.prepared) sends the SAME passage, but as its own earlier turn
    rather than inline here -- so `context` is None even though the question
    is still textbook-grounded, and the caller passes `grounded=True` to say
    so. Getting this wrong silently drops the rule that raised groundedness
    0.179 -> 0.266 (EXP-008): found 2026-09-14 building early priming, where
    the first cut of the new layout scored WORSE than the old one for exactly
    this reason.
    """
    profile = profile or TutorProfile()
    language = profile.language or "English"
    script = {"hindi": "Devanagari", "marathi": "Devanagari"}.get(
        language.strip().lower()
    )
    word_budget = 85 if script == "Devanagari" else 110
    grounded = (context is not None) if grounded is None else grounded

    parts: List[str] = []
    if context:
        parts.append(context)
    parts.append(question)

    # Terse on purpose. These repeat on EVERY turn and are always new tokens, so
    # at ~50ms per new token a wordy reminder costs real seconds per question --
    # measured 2026-09-10. The long-form versions live in the persona, which is
    # cached; this is only the nudge that has to be last, where this model
    # weights instructions hardest.
    rules = ["Plain sentences, one paragraph, no bullets or bold."]
    if grounded:
        # See GROUNDED_ANSWER_RULE's own comment for why this wording, not
        # "in your own words" -- it was right for an inline passage but let
        # the model drift once the passage moved a turn back.
        rules.insert(0, GROUNDED_ANSWER_RULE)
    rules.append("Under {} words.".format(word_budget))
    # The persona already says not to add a question unless it helps, but the
    # persona is ~500 tokens back and this model weights the end of the prompt.
    rules.append("Do not end with a question.")
    if language.strip().lower() != "english":
        rules.append("Reply only in {}{}.".format(
            language, " ({})".format(script) if script else ""
        ))
    if settings.tutor_rules_in_persona:
        # The full rules are in the persona now; the turn keeps only the one this
        # model drops first without a reminder -- the reply language (or, in
        # English, the length). Measured: with no reminder at all, answers ran to
        # 118-159 words.
        #
        # "Write 4-5 full sentences" added 2026-09-14: the persona's "teach"
        # style already says this (STYLE_RULES), but only there -- and
        # measured the same day, real answers were landing at 20-45 decode
        # tokens (one short sentence, the "vague one-line definition" the
        # persona explicitly forbids), which is what a length rule stated
        # ONLY mid-persona and never reinforced at the end gets from this
        # model. A few extra tokens here, every turn, against answers that
        # were quietly too thin to teach from.
        #
        # BEFORE the language/word-budget reminder, not after -- that one has
        # to stay the literal last words of the prompt. Shipped the other
        # order first and measured it break Hindi outright: three straight
        # Hindi questions came back in Marathi, because "Reply only in Hindi"
        # was no longer the end of the prompt, which is what this model
        # weights hardest (the same reason the script clause and the
        # grounding rule already live at the end, not mid-persona).
        tail = rules[-1] if language.strip().lower() != "english" else "Under {} words.".format(word_budget)
        parts.append("Write 4-5 full sentences, not one line. " + tail)
    else:
        parts.append(" ".join(rules))
    return "\n\n".join(parts)


def build_passage_ack(profile: Optional[TutorProfile]) -> str:
    """The tutor's fixed reply to an early-primed passage turn.

    Fixed on purpose -- it is stored in session history and replayed on every
    later turn, so it has to be identical every time or it forks the prefix,
    exactly like a varying persona would. It says nothing the student sees
    time-to-first-audio for: a prime never plays audio, and if the real
    question turns out not to match what was primed (see Session.claim_prepared)
    this whole exchange -- passage, ack and all -- is simply never sent for
    real and never shown.
    """
    language = ((profile.language if profile else None) or "English").strip().lower()
    if language == "marathi":
        return "ठीक आहे."
    if language == "hindi":
        return "ठीक है."
    return "Understood."


def build_chat_messages(
    history: List[Dict[str, str]],
    profile: Optional[TutorProfile],
    context: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Persona, then the conversation.

    `context` is accepted for callers that still pass it (and for the pinned-
    corpus path, where the block genuinely is stable every turn), but the normal
    retrieval path now carries its excerpts inside the user turn -- see
    build_turn_message.
    """
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
