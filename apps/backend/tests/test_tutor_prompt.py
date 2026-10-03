"""The tutor prompt since stage 2 of the golden comparison: AFE-Learning-App's,
byte for byte. Expected strings are copied from AFE's prompts.ts."""

from app.services.tutor import build_tutor_messages

AFE_INSTRUCTIONS = (
    "Patient tutor for a Class 9 student. Subject: Science. Simple words, English, "
    "never invent facts. Most important rule: explain in 5 to 6 plain sentences, "
    "about 100 words. Begin by saying clearly what it is, then explain how or why "
    "it happens, then give one everyday example a student can picture, and end "
    "with one sentence that invites them to think further. Write flowing "
    "sentences only -- no headings, labels, bullet points or numbered parts."
)
AFE_PREAMBLE = (
    "Use the student's textbook excerpts when relevant, prioritizing their "
    "wording and examples over your own knowledge."
)


def test_first_question_is_sent_alone_under_afes_persona():
    system, user = build_tutor_messages("What is inertia?", None, "")
    assert system == {"role": "system", "content": AFE_INSTRUCTIONS}
    assert user == {"role": "user", "content": "What is inertia?"}


def test_excerpts_follow_the_preamble_as_afe_lays_them_out():
    system = build_tutor_messages("q", None, "[1] iesc109\ntext")[0]["content"]
    assert system == "{}\n\n{}\n\n[1] iesc109\ntext".format(AFE_INSTRUCTIONS, AFE_PREAMBLE)


def test_any_second_question_is_wrapped_with_the_first():
    """Even one that names its own topic: AFE wraps every follow-on question."""
    user = build_tutor_messages("What is diffusion?", "What is inertia?", "")[1]["content"]
    assert user == (
        'My earlier question was: "What is inertia?"\n'
        "My follow-up question: What is diffusion?\n"
        "Answer only the follow-up question, and strictly follow the most important "
        "rule: 5 to 6 plain sentences, with one everyday example."
    )
