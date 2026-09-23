"""Compare LLMs on this box: latency and the groundedness proxy, side by side.

Not a correctness harness. `groundedness` here is the same character-trigram
overlap the live metric uses (see services/rag/metrics.py) -- it rewards an
answer for reusing the passage's wording, which is exactly the drift being
chased, but it is not a measure of whether the answer is right. Read the
printed replies, do not just read the table.

Run against a WARM backend and a QUIET box: decode is memory-bandwidth bound,
so anything else running shifts every number here.

    python scripts/benchmark_models.py --models gemma2:2b gemma2:2b-instruct-q4_K_M

One model is fully measured before the next is touched, and the previous one is
unloaded in between -- two 1.7 GB models resident alongside bge-m3's 1.2 GB
does not fit in 8 GB, and the swapping would land in the timings.
"""

import argparse
import csv
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

BACKEND = "http://127.0.0.1:8000"
OLLAMA = "http://127.0.0.1:11434"

# Edit freely -- these must match what is actually ingested in your library,
# or every answer is unaided and `groundedness` comes back null.
QUESTIONS = [
    ("English", "Grade 6", "Science", "What is photosynthesis?"),
    ("English", "Grade 6", "Science", "Why do plants need sunlight?"),
    ("English", "Grade 6", "Science", "What is the function of a cell?"),
    ("Hindi", "Grade 6", "Science", "प्रकाश संश्लेषण क्या है?"),
    ("Hindi", "Grade 6", "Science", "पौधों को सूर्य के प्रकाश की आवश्यकता क्यों होती है?"),
    ("Hindi", "Grade 6", "Science", "कोशिका का क्या कार्य है?"),
]


def _post(url, payload, timeout=300):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def unload(model):
    """Drop `model` from RAM so the next one is not measured against a swap."""
    try:
        _post(
            OLLAMA + "/api/generate",
            {"model": model, "prompt": "", "keep_alive": 0, "stream": False},
            timeout=60,
        )
    except urllib.error.HTTPError:
        pass  # already gone, or never loaded


def ask(model, language, level, subject, message, temperature, max_tokens):
    """One question in its own session -- no history carried between turns."""
    return _post(
        BACKEND + "/api/chat",
        {
            "message": message,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "profile": {
                "language": language,
                "level": level,
                "subject": subject,
                "style": "teach",
            },
        },
    )


def run_model(model, args):
    print("\n" + "=" * 78 + "\n" + model + "\n" + "=" * 78)
    rows = []

    # One throwaway turn so the cold load is not charged to question 1.
    print("  warming...", end="", flush=True)
    t0 = time.perf_counter()
    try:
        ask(model, "English", "Grade 6", "Science", "Hello.", args.temperature, 32)
    except Exception as exc:
        print("\n  FAILED to warm {}: {}".format(model, exc))
        return rows
    print(" {:.1f}s".format(time.perf_counter() - t0))

    for language, level, subject, question in QUESTIONS:
        for run in range(args.runs):
            t0 = time.perf_counter()
            try:
                resp = ask(
                    model, language, level, subject, question,
                    args.temperature, args.max_tokens,
                )
            except Exception as exc:
                print("  ERROR {}: {}".format(question[:40], exc))
                continue
            wall = time.perf_counter() - t0
            m = resp.get("metrics") or {}
            row = {
                "model": model,
                "language": language,
                "question": question,
                "run": run + 1,
                "wall_s": round(wall, 2),
                "prefill_ms": m.get("prefill_ms", 0),
                "prompt_tokens": m.get("prompt_tokens", 0),
                "decode_ms": m.get("decode_ms", 0),
                "completion_tokens": m.get("completion_tokens", 0),
                "tok_per_s": m.get("tokens_per_second", 0.0),
                "load_ms": m.get("load_ms", 0),
                "passages": (m.get("retrieval") or {}).get("returned", 0),
                "groundedness": m.get("groundedness"),
                "note": m.get("groundedness_note", ""),
                "reply": resp.get("reply", ""),
            }
            rows.append(row)
            g = row["groundedness"]
            print(
                "  [{:7}] {:6.1f}s | prefill {:>6}ms ({:>4} tok) | "
                "decode {:>6}ms ({:>3} tok, {:>4.1f} t/s) | "
                "grounded {:<6} | {}".format(
                    language, wall,
                    row["prefill_ms"], row["prompt_tokens"],
                    row["decode_ms"], row["completion_tokens"], row["tok_per_s"],
                    "{:.3f}".format(g) if g is not None else "-",
                    question[:32],
                )
            )
            if args.show_replies:
                print("           -> {}\n".format(row["reply"][:300]))
    return rows


def summarise(rows, args):
    def med(values):
        values = [v for v in values if v is not None]
        return statistics.median(values) if values else None

    print("\n" + "=" * 78 + "\nSUMMARY (medians)\n" + "=" * 78)
    header = "{:<32} {:<8} {:>3} {:>7} {:>8} {:>8} {:>6} {:>9}".format(
        "model", "lang", "n", "wall", "prefill", "decode", "tok/s", "grounded"
    )
    print(header)
    print("-" * len(header))

    for model in dict.fromkeys(r["model"] for r in rows):
        for language in ("English", "Hindi", "ALL"):
            sel = [
                r for r in rows
                if r["model"] == model
                and (language == "ALL" or r["language"] == language)
            ]
            if not sel:
                continue
            g = med([r["groundedness"] for r in sel])
            print(
                "{:<32} {:<8} {:>3} {:>6.1f}s {:>7.0f}ms {:>7.0f}ms "
                "{:>6.1f} {:>9}".format(
                    model, language, len(sel),
                    med([r["wall_s"] for r in sel]),
                    med([r["prefill_ms"] for r in sel]),
                    med([r["decode_ms"] for r in sel]),
                    med([r["tok_per_s"] for r in sel]),
                    "{:.3f}".format(g) if g is not None else "-",
                )
            )
        print()

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print("Per-turn rows -> {}".format(args.out))
    print(
        "\nGroundedness is trigram overlap with the cited passage, not correctness.\n"
        "Read the replies (--show-replies) before trusting the ranking."
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", required=True)
    p.add_argument(
        "--temperature", type=float, default=0.0,
        help="0 isolates the model from sampling noise. Not a production value.",
    )
    p.add_argument("--max-tokens", type=int, default=300)
    p.add_argument("--runs", type=int, default=1, help="Repeats per question.")
    p.add_argument("--out", default="benchmark_results.csv")
    p.add_argument("--show-replies", action="store_true")
    p.add_argument(
        "--no-unload", action="store_true",
        help="Leave each model resident. Only if you have the RAM.",
    )
    args = p.parse_args()

    try:
        urllib.request.urlopen(BACKEND + "/api/health", timeout=5)
    except Exception:
        sys.exit("Backend not reachable at {} -- start it first.".format(BACKEND))

    rows = []
    for i, model in enumerate(args.models):
        rows.extend(run_model(model, args))
        if not args.no_unload and i < len(args.models) - 1:
            unload(model)
            time.sleep(2)

    if rows:
        summarise(rows, args)
    else:
        sys.exit("No successful turns -- check the backend log.")


if __name__ == "__main__":
    main()
