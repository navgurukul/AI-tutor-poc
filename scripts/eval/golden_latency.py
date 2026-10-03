#!/usr/bin/env python3
"""Run the golden question set against a running backend and record every turn.

The 20 questions are AFE-Learning-App's (docs/groundedness/afe-golden.json,
copied from its benchmarks/golden/golden-set.json), asked exactly as typed
through the same /api/chat/stream the app uses, so what this measures is what a
student's turn does. Per question it records:

  retrieval   every passage returned, distance, and whether the budget cut it
  prompt      the exact messages and Ollama options that were sent
  timing      retrieval, TTFT, prefill, decode, load, tokens/s, total
  tokens      prompt tokens and completion (output) tokens
  accuracy    share of the question's `points` found in the answer, and in the
              excerpts the model read (context facts: low on both = retrieval
              missed; low answer / high context = the model ignored the page)

Needs the backend up (apps/backend/run.sh or scripts/start.sh) with turn detail
logging on, which is the default for a developer run (TURN_DETAIL_LOG).

    python3 scripts/eval/golden_latency.py                  # all 20
    python3 scripts/eval/golden_latency.py --only S3,F1     # a subset
    python3 scripts/eval/golden_latency.py --only S3,F1 --label try-1
    python3 scripts/eval/golden_latency.py --repeat 3       # median of 3 per question
    python3 scripts/eval/golden_latency.py --mode cold      # one pass only (default: both)

Two passes, reported separately, because they answer different questions:

  cold   the LLM and the embedding model are unloaded from Ollama before EVERY
         question, so each turn pays the model load (llm load_ms, and a slower
         retrieval) -- what a student gets after the tutor has sat idle.
  warm   both models are unloaded once, loaded and warmed, then all questions
         run back to back. Each prompt is new to Ollama's KV cache, so this is a
         resident model reading a fresh prompt -- not a cached repeat.

Output: apps/backend/logs/golden/<timestamp>[-label]-<cold|warm>/
  summary.md   read first: per-type aggregates and a per-question table
  results.csv  one row per question, with empty manual_grounded_yes_no / manual_notes
  results.json everything, including answers and retrieved passages
  prompts.json the messages sent per question, for comparing with AFE's prompts.json

Follow-ups (F1..F3) continue their parent's session, as in AFE, so list the
parent too when using --only.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "docs" / "groundedness" / "afe-golden.json"
OUT_ROOT = ROOT / "apps" / "backend" / "logs" / "golden"


def http_json(url: str, timeout: float = 30.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def stream_chat(base: str, message: str, session_id: Optional[str], timeout: float) -> Dict[str, Any]:
    """POST /api/chat/stream and fold the SSE frames into one dict."""
    body = {"message": message, "return_context": True}
    if session_id:
        body["session_id"] = session_id
    req = urllib.request.Request(
        base + "/api/chat/stream",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    out: Dict[str, Any] = {"tokens": 0, "error": None}
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            event = json.loads(payload)
            kind = event.get("type")
            if kind == "start":
                out["session_id"] = event["session_id"]
                out["turn_id"] = event.get("turn_id")
                out["model"] = event.get("model")
            elif kind == "sources":
                out["context"] = event.get("context", "")
            elif kind == "token":
                if not out["tokens"]:
                    out["client_ttft_ms"] = int((time.perf_counter() - started) * 1000)
                out["tokens"] += 1
            elif kind == "done":
                out["reply"] = event.get("reply", "")
                out["usage"] = event.get("usage", {})
            elif kind == "error":
                out["error"] = event.get("detail", "unknown error")
    out["client_total_ms"] = int((time.perf_counter() - started) * 1000)
    return out


def ollama_post(host: str, path: str, body: Dict[str, Any], timeout: float = 300.0) -> Any:
    req = urllib.request.Request(
        host + path, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def loaded_models(host: str) -> List[str]:
    return [m["name"] for m in http_json(host + "/api/ps").get("models", [])]


def _same(a: str, b: str) -> bool:
    """"nomic-embed-text" and "nomic-embed-text:latest" are the same model."""
    strip = lambda name: name[: -len(":latest")] if name.endswith(":latest") else name
    return strip(a) == strip(b)


def unload(host: str, models: List[str]) -> None:
    """Evict the models from Ollama and wait until /api/ps no longer lists them."""
    for model in models:
        try:
            ollama_post(host, "/api/generate", {"model": model, "keep_alive": 0}, timeout=60)
        except urllib.error.URLError:
            pass
    deadline = time.time() + 60
    while time.time() < deadline:
        if not any(_same(name, m) for name in loaded_models(host) for m in models):
            return
        time.sleep(0.5)
    print("  ! models still loaded after 60s: {}".format(loaded_models(host)), file=sys.stderr)


def warm(host: str, llm: str, embed: str, num_ctx: int) -> None:
    """Load both models the way the backend will use them (num_ctx must match,
    or Ollama reloads the LLM on the first real request)."""
    ollama_post(host, "/api/chat", {"model": llm, "messages": [], "keep_alive": -1, "options": {"num_ctx": num_ctx}})
    if embed:
        ollama_post(host, "/api/embed", {"model": embed, "input": ["search_query: warmup"], "keep_alive": -1})


def found(points: List[List[str]], text: str) -> float:
    """Share of `points` with at least one accepted substring in `text`."""
    if not points:
        return 0.0
    low = text.lower()
    return sum(any(alt.lower() in low for alt in alts) for alts in points) / len(points)


def run_question(base: str, q: Dict[str, Any], sessions: Dict[str, str], timeout: float) -> Dict[str, Any]:
    parent = q.get("followUpOf")
    session_id = sessions.get(parent) if parent else None
    if parent and not session_id:
        raise RuntimeError("{} is a follow-up of {}; include {} in --only".format(q["id"], parent, parent))

    turn = stream_chat(base, q["question"], session_id, timeout)
    if turn.get("error"):
        raise RuntimeError(turn["error"])
    sessions[q["id"]] = turn["session_id"]

    detail: Dict[str, Any] = {}
    try:
        detail = http_json("{}/api/eval/turns/{}".format(base, turn["turn_id"]))
    except (urllib.error.URLError, ValueError):
        pass  # detail logging off: fall back to the done frame's usage

    llm = detail.get("llm", {})
    usage = turn.get("usage", {})
    retrieval = detail.get("retrieval", {})
    messages = (detail.get("prompt") or {}).get("messages", [])
    context = turn.get("context") or (messages[0]["content"] if messages else "")
    answer = turn.get("reply", "")
    chunks = retrieval.get("chunks", [])
    return {
        "id": q["id"],
        "type": q["type"],
        "class": q.get("class_"),
        "chapter": q.get("chapter"),
        "question": q["question"],
        "turn_id": turn["turn_id"],
        "session_id": turn["session_id"],
        "model": turn.get("model"),
        "retrieval_ms": retrieval.get("ms"),
        "chunks_retrieved": len(chunks),
        "chunks_sent": sum(1 for c in chunks if c["sent"]),
        "context_chars": retrieval.get("context_chars"),
        "top_distance": chunks[0]["distance"] if chunks else None,
        "ttft_ms": llm.get("ttft_ms", turn.get("client_ttft_ms")),
        "prefill_ms": llm.get("prefill_ms", usage.get("prompt_eval_ms")),
        "decode_ms": llm.get("decode_ms", usage.get("eval_ms")),
        "load_ms": llm.get("load_ms", usage.get("load_duration_ms")),
        "prompt_tokens": llm.get("prompt_tokens", usage.get("prompt_tokens")),
        "output_tokens": llm.get("completion_tokens", usage.get("completion_tokens")),
        "tokens_per_second": llm.get("tokens_per_second", usage.get("tokens_per_second")),
        "total_ms": llm.get("total_ms", turn["client_total_ms"]),
        "answer_chars": len(answer),
        "answer_facts": round(found(q.get("points", []), answer), 2),
        "context_facts": round(found(q.get("points", []), context), 2),
        "answer": answer,
        "expected": q.get("answerShouldMention"),
        "chunks": chunks,
        "messages": messages,
        "options": (detail.get("prompt") or {}).get("options"),
    }


def median(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return round(statistics.median(values), 1) if values else None


def mean(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return round(statistics.mean(values), 2) if values else None


def fmt(value: Any) -> str:
    return "-" if value is None else str(value)


def write_outputs(out: Path, rows: List[Dict[str, Any]], args: argparse.Namespace, mode: str = "") -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "prompts.json").write_text(
        json.dumps(
            [{"id": r["id"], "turn_id": r["turn_id"], "options": r["options"], "messages": r["messages"]} for r in rows],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cols = [
        "mode", "id", "type", "class", "chapter", "question", "retrieval_ms", "chunks_retrieved", "chunks_sent",
        "context_chars", "top_distance", "ttft_ms", "prefill_ms", "decode_ms", "load_ms", "prompt_tokens",
        "output_tokens", "tokens_per_second", "total_ms", "answer_chars", "answer_facts", "context_facts",
        "answer",
    ]
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(cols + ["manual_grounded_yes_no", "manual_notes"])
        for r in rows:
            writer.writerow([r.get(c, "") for c in cols] + ["", ""])

    lines = [
        "# Golden set run {} ({} model)".format(args.label or "", mode),
        "",
        "{}  |  model {}  |  {} questions  |  backend {}".format(
            datetime.now().strftime("%Y-%m-%d %H:%M"), rows[0].get("model") if rows else "-", len(rows), args.base_url
        ),
        "",
        "Options sent: `{}`".format(json.dumps(rows[0].get("options")) if rows else "-"),
        "",
        "## By type (medians; facts are means)",
        "",
        "| type | n | load ms | ttft ms | prefill ms | decode ms | prompt tok | output tok | answer facts | context facts |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for kind in ("short", "mid-size", "long", "follow-up", None):
        group = [r for r in rows if kind is None or r["type"] == kind]
        if not group:
            continue
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                kind or "**all**", len(group), fmt(median(group, "load_ms")), fmt(median(group, "ttft_ms")), fmt(median(group, "prefill_ms")),
                fmt(median(group, "decode_ms")), fmt(median(group, "prompt_tokens")),
                fmt(median(group, "output_tokens")), fmt(mean(group, "answer_facts")),
                fmt(mean(group, "context_facts")),
            )
        )
    lines += [
        "",
        "## Per question",
        "",
        "| id | type | retr ms | chunks sent/got | top dist | ttft | prefill | decode | prompt tok | out tok | tok/s | ans facts | ctx facts |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| {} | {} | {} | {}/{} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                r["id"], r["type"], fmt(r["retrieval_ms"]), r["chunks_sent"], r["chunks_retrieved"],
                fmt(r["top_distance"]), fmt(r["ttft_ms"]), fmt(r["prefill_ms"]), fmt(r["decode_ms"]),
                fmt(r["prompt_tokens"]), fmt(r["output_tokens"]), fmt(r["tokens_per_second"]),
                r["answer_facts"], r["context_facts"],
            )
        )
    lines += [
        "",
        "Reading it: low context facts with high answer facts = the model knew it anyway; low on both = "
        "retrieval missed. Keyword facts are a proxy; grade the answers yourself in results.csv.",
    ]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--only", help="comma-separated ids, e.g. S3,F1 (list a follow-up's parent too)")
    ap.add_argument("--label", default="")
    ap.add_argument("--repeat", type=int, default=1, help="runs per question; keeps the median-TTFT run")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--golden", default=str(GOLDEN))
    ap.add_argument("--mode", choices=("both", "cold", "warm"), default="both")
    args = ap.parse_args()
    args.base_url = args.base_url.rstrip("/")

    questions = json.loads(Path(args.golden).read_text(encoding="utf-8"))["questions"]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = wanted - {q["id"] for q in questions}
        if unknown:
            print("Unknown ids: {}".format(", ".join(sorted(unknown))), file=sys.stderr)
            return 2
        questions = [q for q in questions if q["id"] in wanted]

    try:
        http_json(args.base_url + "/health", timeout=5)
    except (urllib.error.URLError, ValueError) as exc:
        print("Backend not reachable at {} ({}). Start it first: apps/backend/run.sh".format(args.base_url, exc), file=sys.stderr)
        return 1
    try:
        http_json(args.base_url + "/api/eval/turns?limit=1", timeout=5)
    except urllib.error.HTTPError as exc:
        print("Turn detail logging is off ({}). Restart the backend with TURN_DETAIL_LOG=true.".format(exc.code), file=sys.stderr)
        return 1

    health = http_json(args.base_url + "/health")
    host = (health.get("ollama") or {}).get("host", "http://localhost:11434").rstrip("/")
    llm = (health.get("model") or {}).get("name")
    embed = (health.get("library") or {}).get("embedding_model") or ""
    turns = http_json(args.base_url + "/api/eval/turns?limit=1")
    num_ctx = 4096
    if turns:
        num_ctx = (turns[0].get("prompt") or {}).get("options", {}).get("num_ctx", num_ctx)
    models = [m for m in (llm, embed) if m]

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    modes = ("cold", "warm") if args.mode == "both" else (args.mode,)
    for mode in modes:
        print("\n== {} pass ({}) ==".format(mode, ", ".join(models)))
        if mode == "warm":
            unload(host, models)
            warm(host, llm, embed, num_ctx)
        rows = run_pass(args, questions, mode, host, models)
        if not rows:
            return 1
        out = OUT_ROOT / "{}{}-{}".format(stamp, "-" + args.label if args.label else "", mode)
        write_outputs(out, rows, args, mode)
        print("Wrote {}  (summary.md first)".format(out))
    return 0


def run_pass(args, questions, mode: str, host: str, models: List[str]) -> List[Dict[str, Any]]:
    sessions: Dict[str, str] = {}
    rows: List[Dict[str, Any]] = []
    print("{:<4} {:<9} {:>7} {:>6} {:>7} {:>8} {:>8} {:>7} {:>7} {:>5} {:>5}".format(
        "id", "type", "retr ms", "chunks", "load", "ttft ms", "prefill", "decode", "out tok", "ans", "ctx"))
    for q in questions:
        try:
            # --repeat re-asks in a fresh session. A follow-up always runs once:
            # repeating it would stack questions in its parent's session.
            attempts = []
            for _ in range(1 if q.get("followUpOf") else max(1, args.repeat)):
                if mode == "cold":
                    unload(host, models)
                attempts.append(run_question(args.base_url, q, sessions, args.timeout))
            attempts.sort(key=lambda r: r["ttft_ms"] or 0)
            row = attempts[len(attempts) // 2]
            row["mode"] = mode
            sessions[q["id"]] = row["session_id"]
        except (RuntimeError, urllib.error.URLError, TimeoutError) as exc:
            print("{:<4} FAILED: {}".format(q["id"], exc), file=sys.stderr)
            continue
        rows.append(row)
        print("{:<4} {:<9} {:>7} {:>3}/{:<2} {:>7} {:>8} {:>8} {:>7} {:>7} {:>5} {:>5}".format(
            row["id"], row["type"], fmt(row["retrieval_ms"]), row["chunks_sent"], row["chunks_retrieved"],
            fmt(row["load_ms"]), fmt(row["ttft_ms"]), fmt(row["prefill_ms"]), fmt(row["decode_ms"]),
            fmt(row["output_tokens"]), row["answer_facts"], row["context_facts"]))
    return rows


if __name__ == "__main__":
    sys.exit(main())
