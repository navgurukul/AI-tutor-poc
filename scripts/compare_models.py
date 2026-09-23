"""Controlled model comparison: the LLM alone, with retrieval taken out of it.

`benchmark_models.py` drives the real backend, so every number it produces also
carries whatever retrieval did that turn -- and on this corpus retrieval misses
often enough (4 of 6 turns on 2026-09-23) that a model A/B run through it is
mostly measuring the library. This script removes that variable: it talks
straight to Ollama and hands every model the SAME question and the SAME
passage, so the only thing left varying is the model.

The passages are real -- consecutive chunks from the ingested book, joined back
into the ~1200-character section they should have been in the first place. That
doubles as a preview of what these models do once chunking is fixed.

Groundedness is computed with the app's own `_trigrams`, so the numbers are
comparable to the turn log's. It measures wording overlap, not correctness.

    python scripts/compare_models.py

Quiet box only: decode is memory-bandwidth bound and anything else running
shifts every row. Roughly 10 minutes for four models.
"""

import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "backend"))
from app.services.rag.metrics import _trigrams  # noqa: E402

OLLAMA = "http://127.0.0.1:11434"
DB = os.path.join(
    os.path.dirname(__file__), "..", "apps", "backend", "data", "library.db"
)

MODELS = [
    ("gemma2:2b", None),                    # Q4_0  -- the long-standing baseline
    ("gemma2:2b-instruct-q4_K_M", None),    # Q4_K_M -- same weights, better quant
    ("llama3.2:3b", None),
    ("qwen3:1.7b", False),                  # False = think off; default is on
]

# (question, document, first ordinal, last ordinal) -- the chunk run that
# actually answers it, joined into one passage.
CASES = [
    ("रेगर मृदा क्या है?", 80, 211, 219),
    ("काली मृदा कहाँ पाई जाती है?", 80, 215, 221),
    ("जलोढ़ मृदा की विशेषताएँ क्या हैं?", 80, 206, 212),
]

SYSTEM = (
    "आप एक शिक्षक हैं। "
    "नीचे दिए गए पाठ का "
    "उपयोग करके उत्तर "
    "दें। केवल हिंदी में "
    "उत्तर दें, लगभग 85 "
    "शब्दों में।"
)


def post(path, payload, timeout=600, stream=False):
    req = urllib.request.Request(
        OLLAMA + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def unload(model):
    try:
        post("/api/generate", {"model": model, "prompt": "", "keep_alive": 0}).read()
    except urllib.error.HTTPError:
        pass


def load_passages():
    import sqlite3

    db = sqlite3.connect(DB)
    out = []
    for question, doc, lo, hi in CASES:
        rows = [
            t
            for (t,) in db.execute(
                "select text from chunks where document_id=? and ordinal between ? and ? "
                "order by ordinal",
                (doc, lo, hi),
            )
        ]
        out.append((question, " ".join(rows)))
    db.close()
    return out


def ask(model, think, question, passage):
    """One streamed turn. Returns timings plus the reply text."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": "पाठ:\n" + passage + "\n\nप्रश्न: " + question,
            },
        ],
        "stream": True,
        "keep_alive": -1,
        "options": {
            "num_ctx": 4096,
            "num_thread": 4,
            "temperature": 0.0,          # isolate the model from sampling noise
            "num_predict": 300,
            "repeat_penalty": 1.15,
            "repeat_last_n": 128,
        },
    }
    if think is not None:
        payload["think"] = think

    started = time.perf_counter()
    ttft = None
    reply = []
    final = {}
    resp = post("/api/chat", payload, stream=True)
    for raw in resp:
        if not raw.strip():
            continue
        frame = json.loads(raw)
        piece = (frame.get("message") or {}).get("content") or ""
        if piece and ttft is None:
            ttft = (time.perf_counter() - started) * 1000.0
        reply.append(piece)
        if frame.get("done"):
            final = frame
    text = "".join(reply).strip()
    ns = 1_000_000.0
    return {
        "reply": text,
        "chars": len(text),
        "ttft_ms": ttft,
        "load_ms": final.get("load_duration", 0) / ns,
        "prompt_tokens": final.get("prompt_eval_count", 0),
        "prefill_ms": final.get("prompt_eval_duration", 0) / ns,
        "completion_tokens": final.get("eval_count", 0),
        "decode_ms": final.get("eval_duration", 0) / ns,
        "total_ms": (time.perf_counter() - started) * 1000.0,
    }


def score(answer, passage):
    """The app's own groundedness: share of the answer's trigrams on the page."""
    a, c = _trigrams(answer), _trigrams(passage)
    if len(a) < 8:
        return None
    return round(len(a & c) / float(len(a)), 3)


def main():
    cases = load_passages()
    print("passages: " + ", ".join(str(len(p)) + " chars" for _, p in cases))
    rows = []

    for model, think in MODELS:
        print("\n" + "=" * 76 + "\n" + model + "\n" + "=" * 76)
        try:
            for question, passage in cases:
                r = ask(model, think, question, passage)
                r["model"] = model
                r["question"] = question
                r["grounded"] = score(r["reply"], passage)
                tok = r["completion_tokens"] or 1
                r["chars_per_token"] = r["chars"] / tok
                r["tok_per_s"] = tok / (r["decode_ms"] / 1000.0 or 1)
                r["chars_per_s"] = r["chars"] / (r["decode_ms"] / 1000.0 or 1)
                rows.append(r)
                print(
                    "  ttft {:>6.0f}ms | prefill {:>6.0f}ms ({:>4} tok) | "
                    "decode {:>6.0f}ms ({:>3} tok) | {:>4.1f} tok/s | "
                    "{:>4.2f} c/tok | {:>5.1f} c/s | grounded {}".format(
                        r["ttft_ms"] or 0, r["prefill_ms"], r["prompt_tokens"],
                        r["decode_ms"], r["completion_tokens"], r["tok_per_s"],
                        r["chars_per_token"], r["chars_per_s"],
                        r["grounded"] if r["grounded"] is not None else "-",
                    )
                )
                print("    " + r["reply"][:160].replace("\n", " "))
        except Exception as exc:
            print("  FAILED: {}".format(exc))
        unload(model)
        time.sleep(2)

    if not rows:
        sys.exit("nothing measured")

    def med(model, key):
        vals = [r[key] for r in rows if r["model"] == model and r[key] is not None]
        return statistics.median(vals) if vals else None

    print("\n" + "=" * 76 + "\nMEDIANS (Hindi, same passage to every model)\n" + "=" * 76)
    head = "{:<28} {:>7} {:>8} {:>7} {:>7} {:>7} {:>9}".format(
        "model", "ttft", "decode", "tok/s", "c/tok", "c/s", "grounded"
    )
    print(head)
    print("-" * len(head))
    for model, _ in MODELS:
        if not any(r["model"] == model for r in rows):
            continue
        g = med(model, "grounded")
        print(
            "{:<28} {:>6.0f}ms {:>7.0f}ms {:>7.1f} {:>7.2f} {:>7.1f} {:>9}".format(
                model, med(model, "ttft_ms") or 0, med(model, "decode_ms"),
                med(model, "tok_per_s"), med(model, "chars_per_token"),
                med(model, "chars_per_s"),
                "{:.3f}".format(g) if g is not None else "-",
            )
        )
    print(
        "\nc/s vs 13.3 = the speech playback rate: below it, audio starves and\n"
        "gaps open mid-answer. Groundedness is wording overlap, not correctness."
    )

    out = os.path.join(os.path.dirname(__file__), "..", "model_comparison.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    print("\nrows -> {}".format(os.path.normpath(out)))


if __name__ == "__main__":
    main()
