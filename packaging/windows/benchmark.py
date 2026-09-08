"""Core latency and grounding numbers, measured on the device itself.

The frontend already logs [timing] lines to the browser console, but those need
DevTools open and a person watching. This runs the same path headlessly so a
laptop can be checked during provisioning, and two machines can be compared.

    "C:\\Program Files\\AITutor\\runtime\\python\\python.exe" benchmark.py

Numbers that matter on a CPU-only device:
  ttft   time to first token -- what a student actually waits for
  total  time to the full reply
  chars/s   generation rate once running
  src    passages retrieved (0 = the answer was ungrounded)
"""

import json
import statistics
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8756"

# Deliberately mixed: two the textbook answers, one it does not, so the run
# reports grounding as well as speed. An off-syllabus question returning 0
# sources is correct behaviour, not a failure.
QUESTIONS = [
    "What is photosynthesis?",
    "What are the three states of matter?",
    "Who won the 2022 football world cup?",
]


def get(path):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as r:
        return json.load(r)


def context_chars(question):
    """How much textbook text this question drags into the prompt.

    Reported alongside the timings because prefill is the dominant cost on this
    hardware -- roughly 27ms per token -- so this column is the one that
    explains a slow ttft, and it is the one RAG_CONTEXT_MAX_CHARS moves.
    """
    body = json.dumps({"question": question}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/library/search",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except Exception:                              # noqa: BLE001
        return 0
    excerpts = data.get("excerpts") or []
    if isinstance(excerpts, str):
        return len(excerpts)
    return sum(len(str(x)) for x in excerpts)


def ask(question):
    """One streamed turn. Returns (ttft, total, chars, n_sources)."""
    body = json.dumps({"message": question}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    ttft = None
    chars = 0
    sources = 0
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            if kind == "sources":
                sources = len(event.get("sources") or [])
            elif kind == "token":
                if ttft is None:
                    ttft = time.perf_counter() - start
                chars += len(event.get("content") or "")
            elif kind == "error":
                print(f"    stream error: {event.get('detail')}")
                break
    return ttft, time.perf_counter() - start, chars, sources


def main():
    try:
        health = get("/health")
    except Exception as exc:                       # noqa: BLE001
        print(f"Backend not reachable at {BASE}: {exc}")
        print("Start the AI Tutor first, then re-run.")
        return 1

    lib = health.get("library") or {}
    print(f"\nbackend   {BASE}   status={health.get('status')}")
    print(f"model     {(health.get('model') or {}).get('name')}   "
          f"ollama={'up' if (health.get('ollama') or {}).get('reachable') else 'DOWN'}")
    print(f"library   available={lib.get('available')}  "
          f"docs={lib.get('documents')}  chunks={lib.get('chunks')}  "
          f"model={lib.get('embedding_model')}")

    # The first turn pays any remaining model load, which is not what a student
    # sees on their second question -- report it, then exclude it.
    print("\nwarming up (first turn absorbs the cold start)...")
    ask("Hello")

    print(f"\n{'question':34} {'ttft':>8} {'total':>8} {'chars/s':>8} {'src':>4} {'ctx':>6}")
    print("-" * 74)
    rows = []
    for q in QUESTIONS:
        ctx = context_chars(q)
        ttft, total, chars, src = ask(q)
        rate = chars / total if total else 0
        rows.append((ttft or 0, total, rate))
        shown = q if len(q) <= 33 else q[:30] + "..."
        print(f"{shown:34} {(ttft or 0):7.2f}s {total:7.2f}s {rate:7.1f} {src:4d} {ctx:6d}")

    print("-" * 74)
    print(f"{'median':34} {statistics.median(r[0] for r in rows):7.2f}s "
          f"{statistics.median(r[1] for r in rows):7.2f}s "
          f"{statistics.median(r[2] for r in rows):7.1f}")
    print("\nttft is what a student waits for; prefill is most of it, at roughly")
    print("27ms per token on this class of hardware. ctx is what retrieval returned")
    print("BEFORE RAG_CONTEXT_MAX_CHARS trims it, so a large ctx with a flat ttft")
    print("means the budget is doing its job. Lower that setting to trade grounding")
    print("for speed; raise it for the reverse.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
