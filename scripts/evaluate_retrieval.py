#!/usr/bin/env python3
"""Measure retrieval, per query language, against a golden set.

Runs against a live backend's POST /api/library/search, which does retrieval
without the model -- so this measures retrieval and nothing else. When the
tutor gives a poor answer the first question is always whether retrieval found
the right passage or the model ignored it, and that is the same separation
this harness needs.

Three modes:

  --report      recall@50, precision@4, MRR and nDCG@4, split by query
                language. This is the baseline every later change is measured
                against; without it, tuning is guesswork.

  --calibrate   on-topic against off-topic distance distributions, per
                language, with the ceiling each one implies. Every ceiling in
                config.py is a starting point until this has been run.

  --check       the two slices that decide whether the gate works: romanized
                Hindi/Marathi, and out-of-syllabus questions whose expected
                result is zero chunks. The second is the only test that can
                tell a working gate from one tuned into permissiveness.

Usage:
    python scripts/evaluate_retrieval.py --golden scripts/golden_set.json --report
    python scripts/evaluate_retrieval.py --golden scripts/golden_set.json --calibrate
    python scripts/evaluate_retrieval.py --golden scripts/golden_set.json --check
"""

import argparse
import json
import math
import statistics
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any, Dict, List, Optional

DEFAULT_BASE = "http://localhost:8000"


def _post(base: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise SystemExit("{} {}: {}".format(path, exc.code, exc.read().decode()[:400]))
    except urllib.error.URLError as exc:
        raise SystemExit(
            "Cannot reach the backend at {}: {}\n"
            "Start it with: cd apps/backend && ./run.sh".format(base, exc.reason)
        )


def _matches(hit: Dict[str, Any], expect: Dict[str, Any]) -> bool:
    """Does this hit satisfy the question's expected-chunk description?

    Matched on heading and page range rather than chunk id, because chunk ids
    are not stable across a re-ingest and a golden set that has to be rebuilt
    every time the chunker changes is a golden set nobody maintains.
    """
    if "heading" in expect and expect["heading"]:
        if expect["heading"].lower() not in (hit.get("heading") or "").lower():
            return False
    if "page" in expect and expect["page"] is not None:
        page = expect["page"]
        if not (hit.get("page_start", 0) <= page <= hit.get("page_end", 0)):
            return False
    if "title" in expect and expect["title"]:
        if expect["title"].lower() not in (hit.get("title") or "").lower():
            return False
    return True


def _dcg(relevances: List[int]) -> float:
    return sum(r / math.log2(i + 2) for i, r in enumerate(relevances))


def _ndcg(relevances: List[int], k: int) -> float:
    actual = _dcg(relevances[:k])
    ideal = _dcg(sorted(relevances, reverse=True)[:k])
    return actual / ideal if ideal else 0.0


def run_report(base: str, golden: List[Dict[str, Any]], k_context: int) -> int:
    by_language: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    unanswerable_failures = []

    for item in golden:
        if item.get("expect_none"):
            continue
        result = _post(base, "/api/library/search", {
            "question": item["question"],
            "grade": item.get("grade"),
            "language": item.get("language"),
            "k": 50,
        })
        hits = result.get("hits", [])
        expect = item.get("expect", {})
        relevances = [1 if _matches(h, expect) else 0 for h in hits]
        rank = next((i + 1 for i, r in enumerate(relevances) if r), None)

        by_language[result.get("query_language", "?")].append({
            "recall_50": 1.0 if rank and rank <= 50 else 0.0,
            "recall_1": 1.0 if rank == 1 else 0.0,
            "precision_4": sum(relevances[:k_context]) / float(k_context),
            "mrr": 1.0 / rank if rank else 0.0,
            "ndcg_4": _ndcg(relevances, k_context),
        })
        if rank is None:
            unanswerable_failures.append((item["question"], result.get("query_language")))

    if not by_language:
        print("No answerable questions in the golden set.")
        return 1

    print()
    print("RETRIEVAL BY QUERY LANGUAGE")
    print("-" * 78)
    print("{:<14}{:>5}{:>11}{:>11}{:>11}{:>9}{:>11}".format(
        "LANGUAGE", "N", "RECALL@50", "RECALL@1", "PREC@4", "MRR", "nDCG@4"))
    print("-" * 78)
    for language in sorted(by_language):
        rows = by_language[language]
        mean = lambda key: statistics.mean(r[key] for r in rows)  # noqa: E731
        print("{:<14}{:>5}{:>11.2f}{:>11.2f}{:>11.2f}{:>9.2f}{:>11.2f}".format(
            language, len(rows), mean("recall_50"), mean("recall_1"),
            mean("precision_4"), mean("mrr"), mean("ndcg_4")))
    print("-" * 78)

    if unanswerable_failures:
        print()
        print("NOT RETRIEVED AT ALL ({}):".format(len(unanswerable_failures)))
        for question, language in unanswerable_failures:
            print("  [{}] {}".format(language, question))
    return 0


def run_calibrate(base: str, golden: List[Dict[str, Any]], grade: Optional[int]) -> int:
    """Correct-chunk vs off-topic distances, per language.

    The on-topic number is the distance of the chunk that actually answers the
    question -- NOT the distance of the best hit. Those are different numbers
    whenever ranking is poor, and conflating them produces a ceiling tuned to
    admit whatever noise happened to rank first. Measured on romanized Hindi,
    best-hit distance said 0.558-0.642 and looked healthy; the correct chunk
    was not in the top 50 at all.

    A question whose correct chunk is never retrieved contributes to
    `unranked` instead, because there is no distance to calibrate against and
    no threshold that can fix it. A high unranked count is a model problem,
    not a threshold problem.
    """
    on: Dict[str, List[float]] = defaultdict(list)
    off: Dict[str, List[float]] = defaultdict(list)
    unranked: Dict[str, int] = defaultdict(int)

    for item in golden:
        result = _post(base, "/api/library/search", {
            "question": item["question"],
            "grade": item.get("grade", grade),
            "language": item.get("language"),
            "raw": True,
            "candidates": 50,
        })
        language = result.get("query_language", "?")
        hits = result.get("hits", [])
        if not hits:
            continue
        if item.get("expect_none"):
            off[language].append(min(h["distance"] for h in hits))
            continue
        expect = item.get("expect", {})
        correct = [h["distance"] for h in hits if _matches(h, expect)]
        if correct:
            on[language].append(min(correct))
        else:
            unranked[language] += 1

    print()
    print("DISTANCE CALIBRATION -- best hit per question")
    print("-" * 78)
    print("{:<14}{:>7}{:>10}{:>10}{:>10}{:>10}{:>13}".format(
        "LANGUAGE", "KIND", "N", "MIN", "MEDIAN", "MAX", "SUGGESTED"))
    print("-" * 78)
    for language in sorted(set(on) | set(off)):
        suggestion = ""
        if on.get(language) and off.get(language):
            gap_lo, gap_hi = max(on[language]), min(off[language])
            suggestion = (
                "{:.2f}".format((gap_lo + gap_hi) / 2)
                if gap_lo < gap_hi
                else "OVERLAP"
            )
        for kind, data in (("on-topic", on.get(language)), ("off-topic", off.get(language))):
            if not data:
                continue
            print("{:<14}{:>7}{:>10}{:>10.3f}{:>10.3f}{:>10.3f}{:>13}".format(
                language, kind, len(data), min(data), statistics.median(data),
                max(data), suggestion if kind == "on-topic" else ""))
    print("-" * 78)
    if unranked:
        print()
        print("CORRECT CHUNK NEVER RETRIEVED (no distance to calibrate against):")
        for language in sorted(unranked):
            print("  {:<12} {} question(s)".format(language, unranked[language]))
        print("  A threshold cannot fix this. It is a ranking failure, and the")
        print("  ceiling that admits these queries admits noise with a citation.")
    print()
    print("SUGGESTED is the midpoint between the worst CORRECT-chunk distance and")
    print("the best off-topic one. OVERLAP means no ceiling separates them.")
    return 0


def run_check(base: str, golden: List[Dict[str, Any]]) -> int:
    """The two slices that decide whether the gate actually works."""
    romanized = [g for g in golden if g.get("slice") == "romanized"]
    out_of_syllabus = [g for g in golden if g.get("expect_none")]
    failures = 0

    print()
    print("OUT-OF-SYLLABUS -- expected result is zero chunks")
    print("-" * 78)
    if not out_of_syllabus:
        print("  none in the golden set -- the gate is untested")
        failures += 1
    for item in out_of_syllabus:
        result = _post(base, "/api/library/search", {
            "question": item["question"],
            "grade": item.get("grade"),
            "language": item.get("language"),
            "k": 4,
        })
        hits = result.get("hits", [])
        ok = len(hits) == 0
        failures += 0 if ok else 1
        print("  {} [{}] {!r} -> {} chunks".format(
            "PASS" if ok else "FAIL", result.get("query_language"),
            item["question"][:44], len(hits)))

    print()
    print("ROMANIZED -- must retrieve what its Devanagari twin retrieves")
    print("-" * 78)
    if not romanized:
        print("  none in the golden set -- the ceilings are untested where they")
        print("  are most likely to be wrong")
        failures += 1
    for item in romanized:
        result = _post(base, "/api/library/search", {
            "question": item["question"],
            "grade": item.get("grade"),
            "language": item.get("language"),
            "k": 4,
        })
        hits = result.get("hits", [])
        expect = item.get("expect", {})
        ok = any(_matches(h, expect) for h in hits)
        failures += 0 if ok else 1
        print("  {} [{}] {!r} -> {} chunks".format(
            "PASS" if ok else "FAIL", result.get("query_language"),
            item["question"][:44], len(hits)))

    print("-" * 78)
    print("{} failing".format(failures) if failures else "all slices pass")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", required=True, help="Golden set JSON.")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--grade", type=int, default=None)
    parser.add_argument("--k-context", type=int, default=4)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    with open(args.golden, encoding="utf-8") as fh:
        golden = json.load(fh)
    if isinstance(golden, dict):
        golden = golden.get("questions", [])
    if args.grade is not None:
        for item in golden:
            item.setdefault("grade", args.grade)

    if not (args.report or args.calibrate or args.check):
        args.report = True

    status = 0
    if args.report:
        status |= run_report(args.base, golden, args.k_context)
    if args.calibrate:
        status |= run_calibrate(args.base, golden, args.grade)
    if args.check:
        status |= run_check(args.base, golden)
    return status


if __name__ == "__main__":
    sys.exit(main())
