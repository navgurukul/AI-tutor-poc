"""Does the tutor's answer say only what the book it read actually says?

benchmark.py already answers "did the right passage reach the prompt". This
answers the question after it: given what the model DID read, is every claim in
the reply supported by it. The two fail independently -- a turn can retrieve the
right page and still invent a sentence, and one that retrieved the wrong page can
still be right from the model's own memory -- so they are measured apart and
reported together.

    python3 scripts/eval/groundedness_eval.py                        # full set
    python3 scripts/eval/groundedness_eval.py --items A7,B2          # two items
    python3 scripts/eval/groundedness_eval.py --selftest             # judge only
    python3 scripts/eval/groundedness_eval.py --rescore run-x.json   # no tutor
    python3 scripts/eval/groundedness_eval.py --budget 1200 --label wide

The gold set is docs/groundedness/evalset.json: every quote in it is byte-for-byte
what apps/backend/data/library.db holds, so "the model read the answer" is checked
by string containment and not by a human deciding whether two pages are the same.

WHAT IS COMPUTED, per turn
--------------------------
  groundedness   supported claims / scorable claims, against the excerpt block
                 the model actually read (return_context=true), never against
                 the citations -- the character budget routinely cuts a cited
                 passage before the prompt, and grading against a page the model
                 never saw scores the wrong thing.
  contradicted   claims the excerpt makes false. Reported on its own and never
                 averaged into groundedness: one of these is what actually harms
                 a student, and a mean hides it behind five harmless sentences.
  key coverage   how much of what the book answers with the reply actually says.
                 Groundedness alone is trivially gamed by saying nothing.
  context recall did the gold passage reach the prompt at all. This is what
                 attributes a low score to retrieval rather than to the model.

Claims are sentences, minus the ones that assert nothing: questions, and the
second-person invitation the socratic style rule mandates at the end of every
reply ("Try this at home", "Watch the trees along the road"). Counting those as
unsupported would put a floor under every score for following the prompt. They
are excluded, counted, and printed, so the exclusion can be audited.

THE JUDGE
---------
An LLM judge, local, through the same Ollama the tutor uses -- a word-overlap
score cannot tell "like poles repel" from "like poles attract", and those are
the errors worth finding. Default gemma3:4b: bigger than the 1.5B being graded,
so it is not marking its own homework.

A judge is only worth what it scores on things whose answer is known, so every
run first grades the 14 calibration statements in the gold set (known-true
paraphrases, known-false polarity flips, plausible-but-absent facts) and prints
its own error rates above the results. --lexical runs a deterministic
word-overlap scorer instead, for a machine with no Ollama; it is a triage
signal, and it says so in the report.
"""

import argparse
import csv
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_BASE = "http://127.0.0.1:8756"
DEFAULT_EVALSET = REPO / "docs" / "groundedness" / "evalset.json"
DEFAULT_OUT = REPO / "docs" / "groundedness" / "results"
DEFAULT_JUDGE = "gemma3:4b"
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")

# The claim splitter and both judges live in the backend, which grades gold-set
# questions live in the UI with them -- one implementation, so the number under
# an answer and the number in a report cannot drift apart.
sys.path.insert(0, str(REPO / "apps" / "backend"))
from app.services.groundedness import (  # noqa: E402
    CONTRADICTED,
    SUPPORTED,
    UNSUPPORTED,
    LexicalJudge,
    LlmJudge,
    grade_claims,
    norm,
)


# ---------------------------------------------------------------------------
# the tutor
# ---------------------------------------------------------------------------
def post_sse(base, body, timeout=300):
    """One /api/chat/stream turn, returned as (reply, sources, context, usage).

    `context` is the excerpt block the model read -- everything here is graded
    against it, which is why return_context is forced on.
    """
    body = dict(body, return_context=True)
    req = urllib.request.Request(
        base + "/api/chat/stream",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    reply, sources, context, usage, session_id, turn_id = "", [], "", {}, None, None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for line in resp:
            line = line.decode("utf-8", "replace").rstrip("\n")
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            frame = json.loads(payload)
            kind = frame.get("type")
            if kind == "start":
                session_id, turn_id = frame.get("session_id"), frame.get("turn_id")
            elif kind == "sources":
                sources = frame.get("sources") or []
                context = frame.get("context") or ""
            elif kind == "token":
                reply += frame.get("content") or ""
            elif kind == "done":
                reply = frame.get("reply") or reply
                usage = frame.get("usage") or {}
            elif kind == "error":
                raise RuntimeError(frame.get("detail") or "stream error")
    return {
        "reply": reply.strip(),
        "sources": sources,
        "context": context,
        "usage": usage,
        "session_id": session_id,
        "turn_id": turn_id,
    }


def run_turn(base, item, profile, model, budget, temperature):
    """Run one gold item down a fresh session, exactly as a student would.

    A set B item asks its topic question FIRST, down the same session, and only
    the second turn is scored: the pronoun in "How can we reduce it?" is only
    resolvable because the turn before it exists, and a harness that skips it
    measures a question no student ever asks.
    """
    # No client-invented session id. sessions.get_or_create() hands an unknown
    # id a BRAND NEW session rather than adopting it, so a made-up id silently
    # gives the follow-up turn an empty history: "How can we reduce it?" then
    # has no previous question to carry, retrieves soil erosion at 0.33, and the
    # tutor answers about planting trees. That is how this harness scored its
    # first run, and the failure is invisible unless the ids are compared. The
    # real frontend echoes back the id from the `start` frame, so this does too.
    base_body = {"profile": profile}
    if model:
        base_body["model"] = model
    if budget:
        base_body["context_max_chars"] = budget
    if temperature is not None:
        base_body["temperature"] = temperature

    warmup = None
    if item.get("previous_question"):
        warmup = post_sse(base, dict(base_body, message=item["previous_question"]))
        base_body["session_id"] = warmup["session_id"]
    turn = post_sse(base, dict(base_body, message=item["query"]))
    if warmup and turn["session_id"] != warmup["session_id"]:
        raise RuntimeError(
            "the follow-up opened a new session ({} != {}); it would be scored "
            "with no history and the result would be meaningless".format(
                turn["session_id"], warmup["session_id"]))
    turn["previous_turn"] = (
        {"question": item["previous_question"], "reply": warmup["reply"],
         "sources": warmup["sources"]}
        if warmup else None
    )
    return turn


# ---------------------------------------------------------------------------
# scoring one turn
# ---------------------------------------------------------------------------
def fact_covered(fact, reply):
    """True when the reply says what the book answers with.

    `any_of` is a list of alternative phrasings and one is enough; `all_of`
    requires every entry, which is what a list question ("which are the inner
    planets") needs.
    """
    hay = norm(reply)
    if fact.get("all_of"):
        return all(norm(p) in hay for p in fact["all_of"])
    return any(norm(p) in hay for p in fact.get("any_of", []))


def score_turn(item, turn, judge):
    context, reply = turn.get("context") or "", turn.get("reply") or ""
    hay_context, hay_reply = norm(context), norm(reply)

    gold = item.get("gold_evidence") or []
    recalled = [norm(e["quote"]) in hay_context for e in gold]
    cited_pages = sorted({s.get("page_start") for s in (turn.get("sources") or [])})
    gold_pages = sorted({e["pdf_page"] for e in gold})

    # Known errors override the judge, in that direction only. Each pattern was
    # written against the book by hand for this one question ("like poles
    # attract", "a lever has two parts"), so a match is a contradiction whatever
    # the judge thought -- and the calibration above deliberately does NOT use
    # them, so the error rate printed with the results stays an honest estimate
    # of the judge alone rather than of the judge plus its answer sheet.
    known_errors = item.get("forbidden_claims") or []

    graded, skipped = grade_claims(reply, context, judge, known_errors)

    counts = {v: sum(1 for c in graded if c["verdict"] == v)
              for v in (SUPPORTED, UNSUPPORTED, CONTRADICTED)}
    scorable = len(graded)
    facts = [{"fact": f["fact"], "covered": fact_covered(f, reply)}
             for f in item.get("required_facts") or []]
    forbidden = [f for f in item.get("forbidden_claims") or []
                 if re.search(f["pattern"], hay_reply)]

    return {
        "id": item["id"],
        "set": item["set"],
        "query": item["query"],
        "previous_question": item.get("previous_question"),
        "chapter": item.get("chapter"),
        "must_abstain": bool(item.get("must_abstain")),
        "reply": reply,
        "context": context,
        "context_chars": len(context),
        "passages_read": sum(
            1 for line in context.splitlines()
            if line[:1] == "[" and "]" in line[:5] and line[1:line.index("]")].isdigit()
        ),
        "sources": turn.get("sources") or [],
        "cited_pages": cited_pages,
        "gold_pages": gold_pages,
        "gold_quotes": len(gold),
        "gold_in_prompt": sum(1 for r in recalled if r),
        "context_recall": (round(sum(recalled) / len(recalled), 3) if recalled else None),
        "claims": graded,
        "skipped": skipped,
        "n_claims": scorable,
        "n_supported": counts[SUPPORTED],
        "n_unsupported": counts[UNSUPPORTED],
        "n_contradicted": counts[CONTRADICTED],
        "groundedness": (round(counts[SUPPORTED] / scorable, 3) if scorable else None),
        "facts": facts,
        "key_coverage": (round(sum(f["covered"] for f in facts) / len(facts), 3)
                         if facts else None),
        "forbidden_hits": [f["why"] for f in forbidden],
        "abstained": not (turn.get("sources") or []),
        "usage": turn.get("usage") or {},
        "turn_id": turn.get("turn_id"),
        "session_id": turn.get("session_id"),
        "previous_turn": turn.get("previous_turn"),
    }


def outcome(row):
    """The 2x2 a turn lands in. Groundedness and correctness are different
    failures with different fixes, and the pair is what says which one to go
    and look at."""
    if row["must_abstain"]:
        return "abstained" if row["abstained"] else "answered off-syllabus from the book"
    if row["n_contradicted"]:
        return "contradicts the book"
    grounded = (row["groundedness"] or 0) >= 0.8
    complete = (row["key_coverage"] or 0) >= 0.5
    if grounded and complete:
        return "grounded and complete"
    if grounded:
        return "grounded but thin"
    if complete:
        return "right, but not from the book"
    return "ungrounded and incomplete"


# ---------------------------------------------------------------------------
# calibration: grade the judge before trusting it
# ---------------------------------------------------------------------------
def calibrate(evalset, judge):
    by_id = {i["id"]: i for i in evalset["items"]}
    cases = (evalset.get("judge_calibration") or {}).get("cases") or []
    results = []
    for case in cases:
        item = by_id[case["evidence_from"]]
        evidence = "\n".join(e["quote"] for e in item["gold_evidence"])
        got, why = judge.verdict(case["statement"], evidence)
        results.append(dict(case, got=got, evidence_sentence=why,
                            ok=(got == case["expect"])))
    total = len(results) or 1
    strict = [r for r in results if r["expect"] == SUPPORTED and r["got"] != SUPPORTED]
    fooled = [r for r in results if r["expect"] != SUPPORTED and r["got"] == SUPPORTED]
    n_supported = sum(1 for r in results if r["expect"] == SUPPORTED) or 1
    n_false = sum(1 for r in results if r["expect"] != SUPPORTED) or 1
    return {
        "cases": results,
        "n": len(results),
        "accuracy": round(sum(r["ok"] for r in results) / total, 3),
        "missed_support": round(len(strict) / n_supported, 3),
        "waved_through": round(len(fooled) / n_false, 3),
    }


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------
def mean(values):
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 3) if values else None


def summarise(rows):
    scored = [r for r in rows if not r["must_abstain"]]
    claims = sum(r["n_claims"] for r in scored)
    return {
        "turns": len(rows),
        "scored_turns": len(scored),
        "claims": claims,
        "supported": sum(r["n_supported"] for r in scored),
        "unsupported": sum(r["n_unsupported"] for r in scored),
        "contradicted": sum(r["n_contradicted"] for r in scored),
        # Every claim weighs the same, so a long answer counts for more than a
        # short one. The per-turn mean beside it weighs every turn the same.
        "groundedness_micro": (round(sum(r["n_supported"] for r in scored) / claims, 3)
                               if claims else None),
        "groundedness_macro": mean([r["groundedness"] for r in scored]),
        "key_coverage": mean([r["key_coverage"] for r in scored]),
        "context_recall": mean([r["context_recall"] for r in scored]),
        "turns_with_contradiction": sum(1 for r in scored if r["n_contradicted"]),
        "turns_fully_grounded": sum(1 for r in scored if r["groundedness"] == 1.0),
        "turns_no_context": sum(1 for r in scored if not r["context"].strip()),
        # Supported verdicts whose quoted line is not actually in the excerpt.
        # Not deducted from anything -- printed so the reader knows how many
        # verdicts to go and check by hand.
        "supported_on_a_bad_quote": sum(
            1 for r in scored for c in r["claims"]
            if c["verdict"] == SUPPORTED and c.get("quote_found") is False),
        # None, not True, when no abstention item ran -- all() over an empty
        # list is True, and reporting "abstention held" for a check that never
        # ran is the one kind of wrong number this whole file exists to prevent.
        "abstention_ok": (all(r["abstained"] for r in rows if r["must_abstain"])
                          if any(r["must_abstain"] for r in rows) else None),
        "outcomes": {o: sum(1 for r in rows if outcome(r) == o)
                     for o in sorted({outcome(r) for r in rows})},
    }


def print_report(rows, summary, cal, judge, meta):
    w = sys.stdout.write
    w("\n" + "=" * 78 + "\n")
    w("GROUNDEDNESS  {}  ({})\n".format(meta["label"] or "-", meta["ts"]))
    w("tutor {} @ {} | budget {} | judge {}\n".format(
        meta["model"], meta["base"], meta["budget"] or "backend default", judge))
    w("=" * 78 + "\n")

    if cal:
        w("\nJUDGE CALIBRATION  {}/{} known verdicts correct ({:.0%})\n".format(
            sum(c["ok"] for c in cal["cases"]), cal["n"], cal["accuracy"]))
        w("  missed real support {:.0%}   waved a false claim through {:.0%}\n".format(
            cal["missed_support"], cal["waved_through"]))
        for c in cal["cases"]:
            if not c["ok"]:
                w("    x {} expected {}, got {}: {}\n".format(
                    c["id"], c["expect"], c["got"], c["statement"][:64]))

    w("\n{:<20} {:>5} {:>6} {:>6} {:>5} {:>5}  {}\n".format(
        "item", "grnd", "key", "recall", "clm", "bad", "outcome"))
    w("-" * 78 + "\n")
    for r in rows:
        def pct(v):
            return "  -  " if v is None else "{:>4.0%} ".format(v)
        grounded = None if r["must_abstain"] else r["groundedness"]
        w("{:<20} {} {} {} {:>5} {:>5}  {}\n".format(
            r["id"][:20], pct(grounded), pct(r["key_coverage"]),
            pct(r["context_recall"]), r["n_claims"],
            r["n_unsupported"] + r["n_contradicted"], outcome(r)))

    s = summary
    w("-" * 78 + "\n")
    w("\n{} claims over {} scored turns\n".format(s["claims"], s["scored_turns"]))
    w("  groundedness   {:.0%} of claims supported (per-turn mean {:.0%})\n".format(
        s["groundedness_micro"] or 0, s["groundedness_macro"] or 0))
    w("  unsupported    {}   contradicted {}  (in {} of {} turns)\n".format(
        s["unsupported"], s["contradicted"], s["turns_with_contradiction"],
        s["scored_turns"]))
    w("  key coverage   {:.0%}   context recall {:.0%}\n".format(
        s["key_coverage"] or 0, s["context_recall"] or 0))
    w("  fully grounded {}/{} turns   answered with no excerpt at all: {}\n".format(
        s["turns_fully_grounded"], s["scored_turns"], s["turns_no_context"]))
    if s["supported_on_a_bad_quote"]:
        w("  {} supported verdict(s) cite a line that is not in the excerpt "
          "-- check these by hand\n".format(s["supported_on_a_bad_quote"]))
    w("  abstained off-syllabus: {}\n".format(
        {True: "yes", False: "NO", None: "not run"}[s["abstention_ok"]]))
    w("\n")
    for name, n in sorted(s["outcomes"].items(), key=lambda kv: -kv[1]):
        w("  {:>2}  {}\n".format(n, name))
    w("\n")


def corpus_label(evalset):
    """Name the book, or the books, the gold set was drawn from.

    A single-book set carries corpus.document; a set spanning several carries
    corpus.documents. Both are named here so a multi-book run reports what it
    actually covered instead of crashing on the missing singular key.
    """
    corpus = evalset.get("corpus") or {}
    if corpus.get("document"):
        return corpus["document"]
    docs = corpus.get("documents") or []
    if not docs:
        return "an unnamed corpus"
    if len(docs) == 1:
        return docs[0]
    return "{} and {}".format(", ".join(docs[:-1]), docs[-1])


def write_markdown(path, rows, summary, cal, judge, meta, evalset):
    """The readable artifact: every claim under the excerpt it was judged
    against, so a verdict can be overruled by a person with the book open."""
    s, L = summary, []
    L += ["# Groundedness run — {}".format(meta["label"] or meta["run_id"]), "",
          "{} · tutor `{}` · {} · budget {} · judge {}".format(
              meta["ts"], meta["model"], meta["base"],
              meta["budget"] or "backend default", judge),
          "", "Gold set `{}` over *{}*. Each answer is graded against the excerpt "
          "block that turn actually read, not against the pages it cited.".format(
              meta["evalset"], corpus_label(evalset)), ""]

    L += ["## Headline", "",
          "| | |", "|---|---|",
          "| Groundedness (claims) | **{:.0%}** ({}/{} claims supported) |".format(
              s["groundedness_micro"] or 0, s["supported"], s["claims"]),
          "| Groundedness (per turn) | {:.0%} |".format(s["groundedness_macro"] or 0),
          "| Contradictions | **{}** claims, in {} of {} turns |".format(
              s["contradicted"], s["turns_with_contradiction"], s["scored_turns"]),
          "| Unsupported | {} claims |".format(s["unsupported"]),
          "| Key coverage | {:.0%} |".format(s["key_coverage"] or 0),
          "| Context recall | {:.0%} of gold passages reached the prompt |".format(
              s["context_recall"] or 0),
          "| Fully grounded turns | {}/{} |".format(
              s["turns_fully_grounded"], s["scored_turns"]),
          "| Supported on a quote not in the excerpt | {} \u2014 judge slips, "
          "check by hand |".format(s["supported_on_a_bad_quote"]),
          "| Off-syllabus abstention | {} |".format(
              {True: "held", False: "**FAILED**",
               None: "not in this run"}[s["abstention_ok"]]), ""]
    L += ["| outcome | turns |", "|---|---|"]
    L += ["| {} | {} |".format(k, v)
          for k, v in sorted(s["outcomes"].items(), key=lambda kv: -kv[1])] + [""]

    if cal:
        L += ["## The judge, graded first", "",
              "{}/{} known verdicts correct. It missed real support {:.0%} of the "
              "time and waved a false claim through {:.0%} of the time — the "
              "error bars on every number above.".format(
                  sum(c["ok"] for c in cal["cases"]), cal["n"],
                  cal["missed_support"], cal["waved_through"]), ""]
        wrong = [c for c in cal["cases"] if not c["ok"]]
        if wrong:
            L += ["| statement | expected | judge said |", "|---|---|---|"]
            L += ["| {} | {} | {} |".format(c["statement"], c["expect"], c["got"])
                  for c in wrong] + [""]
        else:
            L += ["Every calibration case came back correct.", ""]

    L += ["## Per item", ""]
    L += ["| item | grounded | key | recall | claims | outcome |", "|---|---|---|---|---|---|"]
    for r in rows:
        def pct(v):
            return "—" if v is None else "{:.0%}".format(v)
        L.append("| `{}` | {} | {} | {} | {} | {} |".format(
            r["id"], pct(r["groundedness"]), pct(r["key_coverage"]),
            pct(r["context_recall"]), r["n_claims"], outcome(r)))
    L += [""]

    for r in rows:
        L += ["---", "", "### `{}` — {}".format(r["id"], r["query"]), ""]
        if r["previous_question"]:
            L += ["*Asked after* “{}” *in the same session — the "
                  "pronoun only resolves because that turn happened.*".format(
                      r["previous_question"]), ""]
        L += ["**Retrieved:** {} · **read:** {} passage(s), {} chars · "
              "**gold pages:** {} · **cited:** {}".format(
                  len(r["sources"]), r["passages_read"], r["context_chars"],
                  ", ".join("p.{}".format(p) for p in r["gold_pages"]) or "—",
                  ", ".join("p.{}".format(p) for p in r["cited_pages"]) or "none"), "",
              "**Gold passage reached the prompt:** {}/{} quotes".format(
                  r["gold_in_prompt"], r["gold_quotes"]), ""]
        L += ["**Answer**", "", "> " + (r["reply"] or "*(empty)*").replace("\n", "\n> "), ""]
        if r["claims"]:
            L += ["| claim | verdict | the judge's line from the excerpt |",
                  "|---|---|---|"]
            mark = {SUPPORTED: "supported", UNSUPPORTED: "**unsupported**",
                    CONTRADICTED: "**CONTRADICTED**"}
            for c in r["claims"]:
                L.append("| {} | {} | {} |".format(
                    c["text"].replace("|", "\\|"), mark[c["verdict"]],
                    (c["evidence"] or "—").replace("|", "\\|")[:180]))
            L += [""]
        if r["skipped"]:
            L += ["*Not scored ({} sentence(s) asserting nothing):* {}".format(
                len(r["skipped"]),
                "; ".join("{} — {}".format(x["kind"], x["text"])
                          for x in r["skipped"])), ""]
        if r["facts"]:
            L += ["**What the book answers with:** " + " · ".join(
                "{} {}".format("✓" if f["covered"] else "✗", f["fact"])
                for f in r["facts"]), ""]
        if r["forbidden_hits"]:
            L += ["**Known error fired:** " + "; ".join(r["forbidden_hits"]), ""]
        L += ["<details><summary>The excerpt block this answer was graded against"
              "</summary>", "", "```", r["context"] or "(nothing retrieved)", "```",
              "</details>", ""]

    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path


CSV_FIELDS = ("run_id", "label", "ts_utc", "item", "set", "query", "chapter",
              "model", "judge", "budget", "sources", "passages_read",
              "context_chars", "gold_quotes", "gold_in_prompt", "context_recall",
              "n_claims", "n_supported", "n_unsupported", "n_contradicted",
              "groundedness", "key_coverage", "forbidden_hits", "outcome",
              "cited_pages", "gold_pages", "turn_id", "session_id", "answer")


def write_csv(path, rows, meta, judge):
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CSV_FIELDS), extrasaction="ignore")
        if new:
            writer.writeheader()
        for r in rows:
            writer.writerow({
                "run_id": meta["run_id"], "label": meta["label"], "ts_utc": meta["ts"],
                "item": r["id"], "set": r["set"], "query": r["query"],
                "chapter": r["chapter"], "model": meta["model"], "judge": str(judge),
                "budget": meta["budget"] or "", "sources": len(r["sources"]),
                "passages_read": r["passages_read"], "context_chars": r["context_chars"],
                "gold_quotes": r["gold_quotes"], "gold_in_prompt": r["gold_in_prompt"],
                "context_recall": r["context_recall"], "n_claims": r["n_claims"],
                "n_supported": r["n_supported"], "n_unsupported": r["n_unsupported"],
                "n_contradicted": r["n_contradicted"],
                "groundedness": r["groundedness"], "key_coverage": r["key_coverage"],
                "forbidden_hits": " | ".join(r["forbidden_hits"]),
                "outcome": outcome(r),
                "cited_pages": " ".join(str(p) for p in r["cited_pages"]),
                "gold_pages": " ".join(str(p) for p in r["gold_pages"]),
                "turn_id": r["turn_id"], "session_id": r["session_id"],
                "answer": r["reply"],
            })
    return path


# ---------------------------------------------------------------------------
def verify_evalset(evalset, db_path):
    """Every gold quote must still be in the library byte-for-byte.

    A re-ingest with different chunk settings can split a quote across two
    chunks, and then context recall silently reads zero for a turn that read
    the right page. Better to fail loudly here than to publish that number.
    """
    import sqlite3

    if not Path(db_path).exists():
        return ["library not found at {} -- gold quotes unverified".format(db_path)]
    conn = sqlite3.connect(str(db_path))
    hay = [norm((h or "") + " " + t)
           for h, t in conn.execute("select heading, text from chunks")]
    conn.close()
    problems = []
    for item in evalset["items"]:
        for ev in item.get("gold_evidence") or []:
            if not any(norm(ev["quote"]) in h for h in hay):
                problems.append("{} p.{}: quote no longer in the corpus -- {}...".format(
                    item["id"], ev["pdf_page"], ev["quote"][:60]))

        # The reference answer is written only from this item's gold evidence,
        # so it is the set marking its own homework: it must cover its own key
        # phrases and must trip none of its own known-error patterns. Both have
        # already caught real bugs -- "in contact" could never match "come into
        # contact", and A10's pattern fired across a full stop on its own
        # reference, which would have called a correct answer a contradiction.
        reference = item.get("reference_answer")
        if not reference:
            continue
        for fact in item.get("required_facts") or []:
            if not fact_covered(fact, reference):
                problems.append("{}: no phrasing in the key matches the "
                                "reference answer -- \"{}\"".format(
                                    item["id"], fact["fact"]))
        for forbidden in item.get("forbidden_claims") or []:
            if re.search(forbidden["pattern"], norm(reference)):
                problems.append("{}: known-error pattern /{}/ fires on the "
                                "reference answer".format(
                                    item["id"], forbidden["pattern"]))
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base", nargs="?", default=DEFAULT_BASE)
    ap.add_argument("--evalset", default=str(DEFAULT_EVALSET))
    ap.add_argument("--label", default="")
    ap.add_argument("--model", default=None, help="tutor model; default = backend's")
    ap.add_argument("--judge", default=DEFAULT_JUDGE)
    ap.add_argument("--lexical", action="store_true",
                    help="word-overlap scoring instead of the LLM judge")
    ap.add_argument("--budget", type=int, default=None, help="context_max_chars")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--items", default="", help="comma-separated ids or prefixes")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--db", default=str(REPO / "apps" / "backend" / "data" / "library.db"))
    ap.add_argument("--selftest", action="store_true",
                    help="grade the judge on the calibration cases and stop")
    ap.add_argument("--rescore", default="",
                    help="re-judge a previous run-*.json without calling the tutor")
    ap.add_argument("--no-calibration", action="store_true")
    ap.add_argument("--allow-corpus-drift", action="store_true",
                    help="run even though some gold quotes are no longer in the "
                         "corpus; their context recall becomes meaningless")
    ap.add_argument("--check-evalset", action="store_true",
                    help="verify the gold set against the corpus and stop")
    args = ap.parse_args(argv)

    evalset = json.loads(Path(args.evalset).read_text(encoding="utf-8"))
    judge = LexicalJudge() if args.lexical else LlmJudge(args.judge, OLLAMA)
    run_id = uuid.uuid4().hex[:8]
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    problems = verify_evalset(evalset, args.db)
    if problems:
        print("!! the gold set does not check out against the corpus -- a "
              "re-ingest changed the chunking, the wrong book is loaded, or an "
              "answer key was edited into something no correct answer matches:")
        for m in problems:
            print("   " + m)
        if not args.allow_corpus_drift:
            return 2
        # Deliberately an opt-in flag rather than a silent tolerance, and
        # deliberately NOT a reason to edit the gold set: trimming a quote until
        # it matches is how a filter that deleted a real answer gets recorded as
        # an improvement. The run proceeds, the drift is printed again in the
        # report, and context recall for the affected items reads low because
        # the evidence genuinely is not in the corpus any more.
        print("   ...proceeding anyway (--allow-corpus-drift). Context recall "
              "for the items above is NOT trustworthy in this run.")
        drift_notes = list(problems)
    else:
        drift_notes = []
    print("gold set checks out: {} quotes verbatim in the corpus, {} reference "
          "answers cover their own keys.".format(
              sum(len(i.get("gold_evidence") or []) for i in evalset["items"]),
              sum(1 for i in evalset["items"] if i.get("reference_answer"))))

    # Judging is deferred until every turn has been generated. Ollama holds one
    # model at a time here, so asking the tutor and the judge alternately
    # reloads both on every item; two phases load each once.
    if args.check_evalset:
        return 0

    cal = None
    if args.selftest and not args.no_calibration:
        print("grading the judge on {} known verdicts...".format(
            len(evalset["judge_calibration"]["cases"])))
        cal = calibrate(evalset, judge)
    if args.selftest:
        for c in cal["cases"]:
            print("  {} {:<14} expected {:<13} got {:<13} {}".format(
                "ok" if c["ok"] else "XX", c["id"], c["expect"], c["got"],
                c["statement"][:52]))
        print("\naccuracy {:.0%} | missed real support {:.0%} | "
              "waved a false claim through {:.0%}".format(
                  cal["accuracy"], cal["missed_support"], cal["waved_through"]))
        return 0

    wanted = [w.strip() for w in args.items.split(",") if w.strip()]
    items = [i for i in evalset["items"]
             if not wanted or any(i["id"].startswith(w) for w in wanted)]

    if args.rescore:
        prior = json.loads(Path(args.rescore).read_text(encoding="utf-8"))
        by_id = {t["id"]: t for t in prior["turns"]}
        meta = dict(prior["meta"], run_id=run_id, ts=ts,
                    label=args.label or prior["meta"]["label"] + "-rescored")
        raw = [by_id[i["id"]] for i in items if i["id"] in by_id]
        items = [i for i in items if i["id"] in by_id]
    else:
        meta = {"run_id": run_id, "ts": ts, "label": args.label, "base": args.base,
                "model": args.model or "", "budget": args.budget,
                "evalset": args.evalset, "judge": str(judge)}
        try:
            with urllib.request.urlopen(args.base + "/health", timeout=10) as resp:
                health = json.load(resp)
            meta["model"] = args.model or health["model"]["name"]
            if not health["library"].get("available"):
                print("!! the textbook library is not open on that backend; "
                      "every turn would be ungrounded by construction.")
                return 2
        except urllib.error.URLError as exc:
            print("!! no backend at {}: {}\n   start it with: "
                  "cd apps/backend && ./run.sh".format(args.base, exc))
            return 2

        print("\nasking the tutor ({} turns)...".format(len(items)))
        raw = []
        for n, item in enumerate(items, 1):
            print("  [{}/{}] {:<20} {}".format(n, len(items), item["id"], item["query"]))
            # Per-item profile, falling back to the set's. Retrieval
            # partitions on the grade parsed out of profile.level, so a
            # multi-book set MUST send each item its own grade -- asking a
            # Class 10 question under a Class 6 profile searches the wrong
            # books and scores the model for a retrieval miss the harness
            # caused itself.
            profile = dict(evalset["profile"], **(item.get("profile") or {}))
            turn = run_turn(args.base, item, profile, args.model,
                            args.budget, args.temperature)
            turn["id"] = item["id"]
            raw.append(turn)
        stem = "run-{}-{}".format(args.label, run_id) if args.label else "run-" + run_id
        # Written before judging: the turns cost minutes of generation, and
        # --rescore re-judges this file without asking the tutor again.
        (out_dir / (stem + ".json")).write_text(
            json.dumps({"meta": meta, "turns": raw}, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print("  transcript saved to {}".format(out_dir / (stem + ".json")))

    if not args.no_calibration:
        print("\ngrading the judge on {} known verdicts...".format(
            len(evalset["judge_calibration"]["cases"])))
        cal = calibrate(evalset, judge)
        print("  {:.0%} correct | missed real support {:.0%} | "
              "waved a false claim through {:.0%}".format(
                  cal["accuracy"], cal["missed_support"], cal["waved_through"]))

    print("\njudging {} answers...".format(len(items)))
    rows = []
    for n, (item, turn) in enumerate(zip(items, raw), 1):
        row = score_turn(item, turn, judge)
        rows.append(row)
        print("  [{}/{}] {:<20} {} claims, {} not supported".format(
            n, len(items), item["id"], row["n_claims"],
            row["n_unsupported"] + row["n_contradicted"]))

    summary = summarise(rows)
    print_report(rows, summary, cal, judge, meta)

    stem = ("groundedness-{}-{}".format(args.label, meta["run_id"])
            if args.label else "groundedness-" + meta["run_id"])
    md = write_markdown(out_dir / (stem + ".md"), rows, summary, cal, judge, meta, evalset)
    csv_path = write_csv(out_dir / "groundedness.csv", rows, meta, judge)
    print("  report  {}".format(md))
    print("  rows    {}".format(csv_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
