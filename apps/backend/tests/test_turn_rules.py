"""The reply rules live in the cached persona; each turn carries a short reminder.

Sent with every turn, the rules were new tokens every time (56 on a Hindi
textbook turn). In the persona they are cached. These tests pin the layout that
was quality-checked, and keep the persona's copy of the rules in step with the
per-turn one, so switching the setting off restores exactly the old behaviour.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.schemas import TutorProfile  # noqa: E402
from app.services import tutor  # noqa: E402

HINDI = TutorProfile(language="Hindi", level="Class 6", subject="History", style="teach")
ENGLISH = TutorProfile(language="English", level="Class 6", subject="Science", style="teach")
PASSAGE = "Textbook excerpts:\n[1] Scurvy is caused by a lack of vitamin C."


def test_the_turn_keeps_only_a_short_reminder(monkeypatch):
    monkeypatch.setattr(settings, "tutor_rules_in_persona", True)
    assert tutor.build_turn_message("संज्ञा क्या है?", HINDI, PASSAGE) == (
        PASSAGE + "\n\nसंज्ञा क्या है?\n\nReply only in Hindi (Devanagari).")
    assert tutor.build_turn_message("What causes scurvy?", ENGLISH, None) == (
        "What causes scurvy?\n\nUnder 110 words.")


def test_the_persona_ends_with_the_rules(monkeypatch):
    monkeypatch.setattr(settings, "tutor_rules_in_persona", True)
    prompt = tutor.build_system_prompt(HINDI)
    tail = prompt.rsplit("\n\n", 1)[1]
    assert tail.startswith("Rules for every reply: ")
    for rule in tutor._reply_rules(HINDI):
        assert rule in tail
    assert "never mention the text itself" in tail


def test_switched_off_restores_the_old_turn(monkeypatch):
    monkeypatch.setattr(settings, "tutor_rules_in_persona", False)
    turn = tutor.build_turn_message("संज्ञा क्या है?", HINDI, None)
    assert turn == "संज्ञा क्या है?\n\n" + " ".join(tutor._reply_rules(HINDI))
    assert "Rules for every reply" not in tutor.build_system_prompt(HINDI)


def test_the_persona_copy_matches_the_per_turn_rules(monkeypatch):
    # _reply_rules duplicates the strings build_turn_message writes; if one
    # changes without the other, the persona and the old per-turn layout drift.
    monkeypatch.setattr(settings, "tutor_rules_in_persona", False)
    for profile in (HINDI, ENGLISH, TutorProfile(language="Marathi")):
        turn = tutor.build_turn_message("Q", profile, None)
        assert turn.split("\n\n")[-1] == " ".join(tutor._reply_rules(profile))


def test_a_pinned_book_keeps_its_own_closing_rules(monkeypatch):
    monkeypatch.setattr(settings, "tutor_rules_in_persona", True)
    prompt = tutor.build_system_prompt(HINDI, context=PASSAGE)
    assert "Rules for every reply" not in prompt
    assert prompt.rstrip().endswith("not a single Latin letter.")
