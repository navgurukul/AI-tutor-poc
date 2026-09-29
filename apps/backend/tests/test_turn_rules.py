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
    # "Write 4-5 full sentences, not one line." (2026-09-14) became a ~300-word
    # target on 2026-09-29, at the user's request for thorough answers instead
    # of a tight few-sentence reply -- see build_turn_message's own comment.
    # Still goes BEFORE the language/word-budget reminder, not after: shipped
    # the other order first and it broke Hindi outright (three straight
    # Hindi questions answered in Marathi) by bumping "Reply only in Hindi"
    # off the true end of the prompt.
    assert tutor.build_turn_message("संज्ञा क्या है?", HINDI, PASSAGE) == (
        PASSAGE + "\n\nसंज्ञा क्या है?\n\nGive a thorough, detailed answer of at "
        "least 320 words in a few short paragraphs, not one or two lines. "
        "Reply only in Hindi (Devanagari).")
    assert tutor.build_turn_message("What causes scurvy?", ENGLISH, None) == (
        "What causes scurvy?\n\nGive a thorough, detailed answer of at least "
        "300 words in a few short paragraphs, not one or two lines. At least "
        "300 words.")


def test_the_persona_ends_with_the_rules(monkeypatch):
    monkeypatch.setattr(settings, "tutor_rules_in_persona", True)
    prompt = tutor.build_system_prompt(HINDI)
    tail = prompt.rsplit("\n\n", 1)[1]
    assert tail.startswith("Rules for every reply: ")
    for rule in tutor._reply_rules(HINDI):
        assert rule in tail
    assert "mention the text itself" in tail.lower()


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


def test_the_language_reminder_stays_the_literal_last_words(monkeypatch):
    # Regression guard for 2026-09-14: adding the length reminder AFTER the
    # language one (instead of before) shipped once and broke Hindi outright
    # -- three straight Hindi questions came back answered in Marathi, live,
    # because "Reply only in Hindi" was no longer the end of the prompt.
    # Whatever else gets added to this tail in future, the language/word-
    # budget reminder must stay the true last words this model reads.
    monkeypatch.setattr(settings, "tutor_rules_in_persona", True)
    for profile, must_end_with in (
        (HINDI, "Reply only in Hindi (Devanagari)."),
        (TutorProfile(language="Marathi"), "Reply only in Marathi (Devanagari)."),
        (ENGLISH, "At least 300 words."),
    ):
        turn = tutor.build_turn_message("Q", profile, PASSAGE)
        assert turn.endswith(must_end_with), turn
