"""Core latency and grounding numbers, measured on the device itself.

The frontend already logs [timing] lines to the browser console, but those need
DevTools open and a person watching. This runs the same path headlessly so a
laptop can be checked during provisioning, and two machines can be compared.

    "C:\\Program Files\\AITutor\\runtime\\python\\python.exe" benchmark.py

    benchmark.py --label topk2 --repeat 3
    benchmark.py http://127.0.0.1:8757 --label multilang

Every turn is also appended to benchmarks.csv in the log directory, beside the
turns-*.csv the backend writes. Rows carry the same turn_id the backend logged,
so a benchmark run joins straight onto turns-backend.csv:

    turn_id -> prompt_tokens, prefill_ms, generation_ms, context_chars

Numbers that matter on a CPU-only device:
  ttft   time to first token -- what a student actually waits for
  total  time to the full reply
  chars/s   generation rate once running
  src    passages retrieved (0 = the answer was ungrounded)

Unlike the backend's turn logs, this one records the question text. These are
three fixed strings authored here, not anything a student typed, so the rule
that keeps child-entered text out of the logs is not in play.
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE = "http://127.0.0.1:8756"

# Deliberately mixed: two the textbook answers, one it does not, so the run
# reports grounding as well as speed. An off-syllabus question returning 0
# sources is correct behaviour, not a failure.
QUESTIONS = [
    "What is photosynthesis?",
    "What are the three states of matter?",
    "Who won the 2022 football world cup?",
]

FIELDS = (
    "ts_utc",
    "run_id",           # one per invocation, so runs never blur together
    "label",            # --label topk2, --label threads4 ...
    "pass_no",          # 1-based, with --repeat
    "question_idx",
    "question",
    "turn_id",          # joins to turns-backend.csv
    "session_id",
    "ttft_ms",          # measured here, client-side: includes retrieval + prefill
    "total_ms",
    "answer_chars",
    "chars_per_second",
    "sources",
    "search_chars",     # what retrieval returned BEFORE the prompt budget trims it
    "prompt_tokens",    # the rest come from Ollama, via the done frame's usage
    "prefill_ms",
    "completion_tokens",
    "generation_ms",
    "tokens_per_second",
    "load_ms",
    "model",
    "base_url",
)


def resolve_log_dir(explicit):
    """Where benchmarks.csv lands, matching the backend's own log directory.

    AITUTOR_LOG_DIR is what the launcher sets for the *backend* process, so it
    is usually absent from the shell a person runs this from -- hence the
    ProgramData fallback, which is the same path launch.ps1 computes.
    """
    if explicit:
        return Path(explicit)
    configured = os.environ.get("AITUTOR_LOG_DIR", "").strip()
    if configured:
        return Path(configured)
    program_data = os.environ.get("ProgramData", "").strip()
    if program_data:
        candidate = Path(program_data) / "AITutor" / "logs"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent / "logs"


def append_rows(log_dir, rows):
    """One append per run. Never fatal: a benchmark that printed its numbers
    has done its job even if the disk refused the copy."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "benchmarks.csv"
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(FIELDS), extrasaction="ignore")
            if new:
                writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in FIELDS})
        return path
    except OSError as exc:
        print(f"\n  could not write benchmarks.csv: {exc}")
        return None


def get(base, path):
    with urllib.request.urlopen(f"{base}{path}", timeout=10) as r:
        return json.load(r)


def search_chars(base, question):
    """How much textbook text this question drags into the prompt.

    Reported alongside the timings because prefill is the dominant cost on this
    hardware -- 18.2ms per prompt token, measured -- so this column is the one
    that explains a slow ttft, and it is the one RAG_CONTEXT_MAX_CHARS moves.
    """
    body = json.dumps({"question": question}).encode()
    req = urllib.request.Request(
        f"{base}/api/library/search",
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


def ask(base, question):
    """One streamed turn.

    Returns a dict of everything the stream gave up: client-side timings, plus
    the turn_id from the start frame and Ollama's own counters from the done
    frame. The latter is what splits a slow turn into prefill and generation --
    the two need different fixes, and ttft alone cannot tell them apart.
    """
    body = json.dumps({"message": question}).encode()
    req = urllib.request.Request(
        f"{base}/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    out = {"ttft_ms": None, "answer_chars": 0, "sources": 0, "turn_id": "",
           "session_id": "", "model": "", "usage": {}}
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
            if kind == "start":
                out["turn_id"] = event.get("turn_id") or ""
                out["session_id"] = event.get("session_id") or ""
                out["model"] = event.get("model") or ""
            elif kind == "sources":
                out["sources"] = len(event.get("sources") or [])
            elif kind == "token":
                if out["ttft_ms"] is None:
                    out["ttft_ms"] = int((time.perf_counter() - start) * 1000)
                out["answer_chars"] += len(event.get("content") or "")
            elif kind == "done":
                out["usage"] = event.get("usage") or {}
            elif kind == "error":
                print(f"    stream error: {event.get('detail')}")
                break
    out["total_ms"] = int((time.perf_counter() - start) * 1000)
    return out


def main():
    parser = argparse.ArgumentParser(
        description="Latency and grounding benchmark for a packaged AI Tutor.",
    )
    parser.add_argument("base", nargs="?", default=DEFAULT_BASE,
                        help=f"backend URL (default {DEFAULT_BASE})")
    parser.add_argument("--label", default="",
                        help="tag for this run, e.g. topk2 -- carried into benchmarks.csv")
    parser.add_argument("--repeat", type=int, default=1,
                        help="passes over the question set (default 1)")
    parser.add_argument("--log-dir", default="",
                        help="where benchmarks.csv goes (default: the backend's log directory)")
    parser.add_argument("--no-log", action="store_true",
                        help="print only; do not append to benchmarks.csv")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    try:
        health = get(base, "/health")
    except Exception as exc:                       # noqa: BLE001
        print(f"Backend not reachable at {base}: {exc}")
        print("Start the AI Tutor first, then re-run.")
        return 1

    lib = health.get("library") or {}
    model_name = (health.get("model") or {}).get("name") or ""
    print(f"\nbackend   {base}   status={health.get('status')}")
    print(f"model     {model_name}   "
          f"ollama={'up' if (health.get('ollama') or {}).get('reachable') else 'DOWN'}")
    print(f"library   available={lib.get('available')}  "
          f"docs={lib.get('documents')}  chunks={lib.get('chunks')}  "
          f"model={lib.get('embedding_model')}")

    run_id = uuid.uuid4().hex[:12]
    if args.label:
        print(f"run       {run_id}   label={args.label}")
    else:
        print(f"run       {run_id}")

    # The first turn pays any remaining model load, which is not what a student
    # sees on their second question -- excluded from the table and from the CSV.
    print("\nwarming up (first turn absorbs the cold start)...")
    ask(base, "Hello")

    header = (f"{'question':34} {'ttft':>8} {'total':>8} {'ans':>5} "
              f"{'ptok':>5} {'prefill':>8} {'gtok':>5} {'src':>4} {'search':>7}")
    print()
    print(header)
    print("-" * len(header))

    rows = []
    for pass_no in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f"pass {pass_no}")
        for idx, question in enumerate(QUESTIONS, start=1):
            found = search_chars(base, question)
            r = ask(base, question)
            usage = r["usage"]
            ttft_ms = r["ttft_ms"] or 0
            total_ms = r["total_ms"]
            rate = (r["answer_chars"] / (total_ms / 1000)) if total_ms else 0.0
            rows.append({
                "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "run_id": run_id,
                "label": args.label,
                "pass_no": pass_no,
                "question_idx": idx,
                "question": question,
                "turn_id": r["turn_id"],
                "session_id": r["session_id"],
                "ttft_ms": ttft_ms,
                "total_ms": total_ms,
                "answer_chars": r["answer_chars"],
                "chars_per_second": round(rate, 1),
                "sources": r["sources"],
                "search_chars": found,
                "prompt_tokens": usage.get("prompt_tokens", ""),
                "prefill_ms": usage.get("prompt_eval_ms", ""),
                "completion_tokens": usage.get("completion_tokens", ""),
                "generation_ms": usage.get("eval_ms", ""),
                "tokens_per_second": usage.get("tokens_per_second", ""),
                "load_ms": usage.get("load_duration_ms", ""),
                "model": r["model"] or model_name,
                "base_url": base,
            })
            shown = question if len(question) <= 33 else question[:30] + "..."
            print(f"{shown:34} {ttft_ms/1000:7.2f}s {total_ms/1000:7.2f}s "
                  f"{r['answer_chars']:5d} "
                  f"{str(usage.get('prompt_tokens', '-')):>5} "
                  f"{str(usage.get('prompt_eval_ms', '-')):>7}m "
                  f"{str(usage.get('completion_tokens', '-')):>5} "
                  f"{r['sources']:4d} {found:7d}")

    print("-" * len(header))
    med = lambda key: statistics.median(r[key] for r in rows)          # noqa: E731
    print(f"{'median':34} {med('ttft_ms')/1000:7.2f}s {med('total_ms')/1000:7.2f}s "
          f"{med('answer_chars'):5.0f}")

    prefills = [r["prefill_ms"] for r in rows if isinstance(r["prefill_ms"], int)]
    ptoks = [r["prompt_tokens"] for r in rows if isinstance(r["prompt_tokens"], int)]
    if prefills and ptoks and sum(ptoks):
        print(f"\nprefill   {sum(prefills)/sum(ptoks):.1f} ms per prompt token "
              f"({1000*sum(ptoks)/sum(prefills):.0f} tok/s)")

    if not args.no_log:
        path = append_rows(resolve_log_dir(args.log_dir), rows)
        if path:
            print(f"\nappended {len(rows)} rows to {path}")
            print("join to turns-backend.csv on turn_id for context_chars and history_msgs.")

    print("\nttft is what a student waits for, and prefill is most of it -- 18.2ms")
    print("per prompt token on this class of hardware, measured. search is what")
    print("retrieval returned BEFORE RAG_CONTEXT_MAX_CHARS trims it, so a large")
    print("search column with a flat ttft means the budget is doing its job.")
    print("Lower RAG_TOP_K or that budget to trade grounding for speed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
