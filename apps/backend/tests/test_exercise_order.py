"""Exercises rank behind explanations, but are never dropped."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.retrieval import _explanations_first, looks_like_exercise  # noqa: E402
from app.services.rag.store import Retrieved  # noqa: E402


def _hit(cid, text, distance=0.3):
    return Retrieved(chunk_id=cid, text=text, heading="", page_start=1, page_end=1,
                     distance=distance, document_title="t", grade=6, subject="s", language="Hindi")


EXERCISE = "(क) इस वाक्य में संज्ञा शब्द कौन-सा है? (ख) कौन-सा शब्द गुण बताता है? ........"
STORY = ("उज्जैन की प्राचीन और ऐतिहासिक नगरी के बाहर एक लंबा-चौड़ा मैदान था। यहाँ-वहाँ "
         "टीले थे। एक दिन लड़कों का एक झुंड वहाँ खेल रहा था।")
ACTIVITY = "Activity 5.7: Let us identify. Look at the picture. Tick the right box. (a) ... (b) ..."
PROSE = "Scurvy is caused due to deficiency of Vitamin C, found in citrus fruits like lemons."


def test_detects_workbook_items_and_not_prose():
    assert looks_like_exercise(EXERCISE)
    assert looks_like_exercise(ACTIVITY)
    assert not looks_like_exercise(STORY)
    assert not looks_like_exercise(PROSE)


def test_explanations_move_ahead_of_a_better_ranked_exercise():
    ordered = _explanations_first([_hit(1, EXERCISE), _hit(2, STORY), _hit(3, ACTIVITY), _hit(4, PROSE)])
    assert [h.chunk_id for h in ordered] == [2, 4, 1, 3]


def test_an_exercise_alone_is_still_returned():
    assert [h.chunk_id for h in _explanations_first([_hit(1, EXERCISE)])] == [1]


def test_a_much_less_relevant_explanation_does_not_jump_an_exercise():
    # The "types of motion" case: an activity on linear motion at 0.364 must not
    # lose its place to "The SI unit of length is metre" at 0.371+0.03 away.
    ordered = _explanations_first([_hit(1, ACTIVITY, 0.364), _hit(2, PROSE, 0.40)])
    assert [h.chunk_id for h in ordered] == [1, 2]


def test_a_lexical_only_hit_never_displaces_anything():
    ordered = _explanations_first([_hit(1, EXERCISE, 0.45), _hit(2, STORY, 1.0)])
    assert [h.chunk_id for h in ordered] == [1, 2]

# The answer to "संसाधनों के वर्गीकरण", as the Class 10 Geography book prints it.
CLASSIFICATION = ("(क) उत्पत्ति के आधार पर - जैव और अजैव (ख) समाप्यता के आधार पर - नवीकरण योग्य "
                  "और अनवीकरण योग्य (ग) स्वामित्व के आधार पर - व्यक्तिगत, सामुदायिक, राष्ट्रीय "
                  "और अंतर्राष्ट्रीय (घ) विकास के स्तर के आधार पर - संभावी, विकसित भंडार और संचित कोष")
# An end-of-chapter exercise: numbered multiple-choice questions.
MCQ = ("(i) लौह अयस्क किस प्रकार का संसाधन है? (क) नवीकरण योग्य (ख) प्रवाह "
       "(ii) ज्वारीय ऊर्जा निम्नलिखित में से किस प्रकार का संसाधन है? (क) पुनः पूर्ति योग्य (ख) अजैव")


def test_an_enumerated_explanation_is_not_an_exercise():
    # Lettered parts alone are how a chapter lists what it teaches.
    assert not looks_like_exercise(CLASSIFICATION)


def test_a_numbered_question_list_is_an_exercise():
    assert looks_like_exercise(MCQ)


def test_one_rhetorical_question_does_not_make_an_exercise():
    text = "क्या आप भी संसाधनों को प्राकृतिक उपहार समझते हैं? (क) जैव (ख) अजैव"
    assert not looks_like_exercise(text)
