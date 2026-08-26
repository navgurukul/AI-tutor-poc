"""End-to-end smoke test against a running backend.

Usage:
    ./.venv/bin/python smoke_test.py [base_url]

Exercises every endpoint the frontend uses and prints a PASS/FAIL summary.
Requires the server to be running and Ollama to be up with the model pulled.
"""

import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
results = []


def call(method, path, payload=None, timeout=240):
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def check(name, condition, detail=""):
    results.append((name, condition))
    print("  %s  %s%s" % ("PASS" if condition else "FAIL", name, ("  -- " + detail) if detail and not condition else ""))


print("Testing %s\n" % BASE)

# --- health -----------------------------------------------------------------
print("health")
status, body = call("GET", "/health", timeout=30)
check("GET /health returns 200", status == 200, str(status))
check("Ollama reachable", body.get("ollama", {}).get("reachable") is True, json.dumps(body.get("ollama")))
check("model available", body.get("model", {}).get("available") is True, json.dumps(body.get("model")))
if not body.get("model", {}).get("available"):
    print("\nModel is unavailable -- run `ollama pull qwen2.5:1.5b` and retry.")
    sys.exit(1)

status, body = call("GET", "/api/models", timeout=30)
check("GET /api/models lists models", status == 200 and len(body.get("models", [])) > 0)

# --- chat -------------------------------------------------------------------
print("\nchat")
t0 = time.time()
status, body = call("POST", "/api/chat", {"message": "In one sentence, what is gravity?", "profile": {"level": "Grade 6", "style": "direct"}})
check("POST /api/chat returns 200", status == 200, str(body)[:200])
check("reply is non-empty", bool(body.get("reply")))
check("usage reports tokens/sec", body.get("usage", {}).get("tokens_per_second", 0) > 0)
sid = body.get("session_id")
check("session_id returned", bool(sid))
print("       (%.1fs, %s tok/s)" % (time.time() - t0, body.get("usage", {}).get("tokens_per_second")))

status, body = call("POST", "/api/chat", {"message": "Say that again more simply.", "session_id": sid})
check("follow-up reuses the session", status == 200 and body.get("session_id") == sid)
check("history grows the prompt", body.get("usage", {}).get("prompt_tokens", 0) > 0)

status, _ = call("POST", "/api/chat", {"message": ""})
check("empty message rejected with 422", status == 422, str(status))

status, body = call("POST", "/api/chat", {"message": "hi", "model": "does-not-exist:1b"}, timeout=30)
check("unknown model returns 404 + hint", status == 404 and bool(body.get("hint")), str(status))

# --- streaming --------------------------------------------------------------
print("\nstreaming")
req = urllib.request.Request(
    BASE + "/api/chat/stream",
    data=json.dumps({"message": "Count to three.", "profile": {"style": "direct"}}).encode(),
    headers={"Content-Type": "application/json"},
)
events, tokens = [], []
with urllib.request.urlopen(req, timeout=240) as r:
    for raw in r:
        line = raw.decode().strip()
        if not line.startswith("data: "):
            continue
        chunk = line[6:]
        if chunk == "[DONE]":
            events.append("DONE")
            break
        event = json.loads(chunk)
        events.append(event.get("type"))
        if event.get("type") == "token":
            tokens.append(event["content"])
check("stream opens with a start event", events and events[0] == "start", str(events[:3]))
check("stream delivers tokens", len(tokens) > 0)
check("stream sends done", "done" in events)
check("stream terminates with [DONE]", events[-1] == "DONE")

# --- tutor ------------------------------------------------------------------
print("\ntutor")
status, body = call("POST", "/api/tutor/explain", {"topic": "Photosynthesis", "level": "Grade 8"})
check("POST /api/tutor/explain returns 200", status == 200, str(body)[:200])
check("explain has 3-5 key points", 3 <= len(body.get("key_points", [])) <= 5, str(len(body.get("key_points", []))))
check("explain has analogy + check question", bool(body.get("analogy")) and bool(body.get("check_question")))

status, body = call("POST", "/api/tutor/quiz", {"topic": "The water cycle", "num_questions": 2, "num_options": 4})
check("POST /api/tutor/quiz returns 200", status == 200, str(body)[:200])
qs = body.get("questions", [])
check("quiz returns 2 questions", len(qs) == 2, str(len(qs)))
check("every question has 4 options", all(len(q["options"]) == 4 for q in qs))
check("answer_index in range", all(0 <= q["answer_index"] < len(q["options"]) for q in qs))

status, body = call("POST", "/api/tutor/evaluate", {"question": "Why do we have seasons?", "student_answer": "Because Earth gets closer to the sun.", "expected_answer": "Because Earth's axis is tilted."})
check("POST /api/tutor/evaluate returns 200", status == 200, str(body)[:200])
check("verdict is valid", body.get("verdict") in ("correct", "partially_correct", "incorrect"), str(body.get("verdict")))
check("score is 0-100", isinstance(body.get("score"), int) and 0 <= body["score"] <= 100)

# --- sessions ---------------------------------------------------------------
print("\nsessions")
status, body = call("GET", "/api/sessions", timeout=30)
check("GET /api/sessions returns a list", status == 200 and isinstance(body, list))
status, body = call("GET", "/api/sessions/" + sid, timeout=30)
check("GET transcript returns messages", status == 200 and len(body.get("messages", [])) >= 4, str(len(body.get("messages", []))))
status, body = call("DELETE", "/api/sessions/" + sid, timeout=30)
check("DELETE session works", status == 200 and body.get("deleted") is True)
status, _ = call("GET", "/api/sessions/" + sid, timeout=30)
check("deleted session returns 404", status == 404, str(status))

# --- summary ----------------------------------------------------------------
passed = sum(1 for _, ok in results if ok)
total = len(results)
print("\n%d/%d checks passed" % (passed, total))
sys.exit(0 if passed == total else 1)
