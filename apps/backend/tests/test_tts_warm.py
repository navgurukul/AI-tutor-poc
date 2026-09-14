"""One voice, one cache entry, one warm-up.

The voice cache holds a single engine. Keyed on the raw language string,
"Hindi" and "hindi" were two entries for one folder and evicted each other --
a full reload on a switch that was not a switch. And a voice that was loaded
but never spoken still made the student's first sentence pay onnxruntime's
first-inference cost, because the lobby only loaded it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import tts  # noqa: E402


class _FakeEngine:
    def __init__(self):
        self.spoken = 0

    def generate(self, text, sid=0, speed=1.0):
        self.spoken += 1
        return type("Audio", (), {"samples": [0.0] * 10, "sample_rate": 16000})()


def _install_fake(monkeypatch):
    loads = []

    def fake_loader(language):
        loads.append(language)
        return _FakeEngine()

    from functools import lru_cache

    monkeypatch.setattr(tts, "_load_engine", lru_cache(maxsize=1)(fake_loader))
    monkeypatch.setattr(tts, "_warmed_key", None)
    monkeypatch.setattr(tts, "_warmup_text", lambda language: "नमस्ते")
    return loads


def test_spellings_of_one_language_share_one_voice(monkeypatch):
    loads = _install_fake(monkeypatch)
    first = tts._engine("Hindi")
    assert tts._engine("hindi") is first
    assert tts._engine(" HINDI ") is first
    assert loads == ["hindi"]


def test_warm_speaks_once_per_loaded_voice(monkeypatch):
    _install_fake(monkeypatch)
    assert tts.warm("Hindi") is True
    engine = tts._engine("hindi")
    assert engine.spoken == 1
    assert tts.warm("hindi") is True  # already warm: no second throwaway sentence
    assert engine.spoken == 1


def test_a_reload_needs_warming_again(monkeypatch):
    loads = _install_fake(monkeypatch)
    tts.warm("Hindi")
    tts.warm("English")  # maxsize=1: evicts Hindi
    tts.warm("Hindi")    # reloaded, so it must be spoken again
    assert loads == ["hindi", "english", "hindi"]
    assert tts._engine("hindi").spoken == 1


def test_a_real_sentence_counts_as_the_warm_up(monkeypatch):
    _install_fake(monkeypatch)
    tts.synthesize("पहला वाक्य", "Hindi")
    engine = tts._engine("hindi")
    spoken = engine.spoken
    tts.warm("Hindi")
    assert engine.spoken == spoken
