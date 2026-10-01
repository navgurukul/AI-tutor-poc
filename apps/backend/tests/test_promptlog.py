"""prompts.jsonl carries the exact messages sent, plus their raw length.

`prompt_chars` is the raw character count of what was actually sent -- summed
across every message's content -- not a token estimate, so it can be read
straight off the log without re-tokenising anything.
"""

import json

from app.config import settings
from app.services import promptlog


def _enable_and_redirect(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "prompt_log_enabled", True)
    monkeypatch.setattr(promptlog, "_logs_dir", lambda: tmp_path)
    return tmp_path / promptlog.FILENAME


def test_prompt_chars_sums_every_message_content(monkeypatch, tmp_path):
    path = _enable_and_redirect(monkeypatch, tmp_path)
    messages = [
        {"role": "system", "content": "abc"},
        {"role": "user", "content": "defgh"},
    ]
    promptlog.log_prompt(messages, "reply", "test-model")
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["prompt_chars"] == len("abc") + len("defgh")
    assert row["messages"] == messages


def test_prompt_chars_is_zero_for_no_messages(monkeypatch, tmp_path):
    path = _enable_and_redirect(monkeypatch, tmp_path)
    promptlog.log_prompt([], None, "test-model")
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["prompt_chars"] == 0


def test_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(promptlog, "_logs_dir", lambda: tmp_path)
    monkeypatch.setattr(settings, "prompt_log_enabled", False)
    promptlog.log_prompt([{"role": "user", "content": "x"}], "y", "m")
    assert not (tmp_path / promptlog.FILENAME).exists()
