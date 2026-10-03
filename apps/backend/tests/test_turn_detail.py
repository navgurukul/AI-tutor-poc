"""The turn record and the Ollama options the golden-set comparison depends on."""

from app.config import Settings, settings
from app.services import turndetail
from app.services.ollama_client import OllamaClient
from app.services.rag.store import Retrieved


def hit(chunk_id: int, text: str, distance: float = 0.2) -> Retrieved:
    return Retrieved(
        chunk_id=chunk_id, text=text, heading="Inertia", page_start=3, page_end=3,
        distance=distance, document_title="iesc109", grade=9, subject="Science",
    )


def test_generation_defaults_match_afe():
    """Stage 2 of the golden comparison: AFE-Learning-App's sampling and cap.
    Read from the class so a developer's .env cannot change the answer."""
    d = Settings(_env_file=None)
    assert (d.max_tokens, d.llm_top_k, d.llm_top_p, d.llm_repeat_penalty, d.llm_repeat_last_n) == (
        512, 20, 0.8, 1.05, 256)


def test_unset_sampling_options_are_not_sent(monkeypatch):
    monkeypatch.setattr(settings, "llm_top_k", None)
    assert "top_k" not in OllamaClient.options()


def test_options_respect_per_request_overrides():
    options = OllamaClient.options(temperature=0.9, max_tokens=64)
    assert options["temperature"] == 0.9
    assert options["num_predict"] == 64


def test_cut_passage_is_marked_not_sent():
    hits = [hit(1, "full text of the first passage"), hit(2, "second passage the budget dropped")]
    rows = turndetail.retrieved_chunks(hits, shown=[hits[0]])
    assert [r["sent"] for r in rows] == [True, False]
    assert rows[1]["chars_sent"] == 0 and rows[1]["excerpt"] is None
    assert rows[1]["chars_retrieved"] == len(hits[1].text)


def test_recent_is_bounded_and_newest_first(monkeypatch, tmp_path):
    monkeypatch.setenv("AITUTOR_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "turn_detail_log", True)
    turndetail._recent.clear()
    for i in range(turndetail.RECENT_LIMIT + 5):
        turndetail.record({"turn_id": "t{}".format(i), "question": "q"})
    assert turndetail.get("t0") is None
    assert turndetail.recent(2)[0]["turn_id"] == "t{}".format(turndetail.RECENT_LIMIT + 4)
    assert (tmp_path / "turns.jsonl").exists()
    turndetail._recent.clear()


def test_record_is_off_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("AITUTOR_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "turn_detail_log", False)
    turndetail.record({"turn_id": "x", "question": "q"})
    assert turndetail.get("x") is None
    assert not (tmp_path / "turns.jsonl").exists()
