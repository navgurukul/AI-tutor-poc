#!/usr/bin/env python3
"""Score this repo's golden runs by AFE-Learning-App's own rules and put them
beside AFE's benchmark, in one sheet of docs/golden-comparison.xlsx.

    python3 scripts/eval/afe_scorecard.py \\
        --run "Now=apps/backend/logs/golden/<stage3>-warm" \\
        --run "Baseline=apps/backend/logs/golden/<stage1>-warm" \\
        --speech apps/backend/logs/golden/<run>-speech

The rules, copied from AFE (benchmarks/golden/run.mjs, ai-tutor/src/groundedness.ts):

  answer facts    share of the question's `points` with an accepted substring in
                  the answer (case-insensitive)
  context facts   the same, over the retrieved passages' text (labels excluded)
  groundedness    character-trigram overlap of the answer's content words with
                  the passages: filler words and bare numbers dropped, words of
                  three letters or fewer kept whole; None with no passages or
                  fewer than 8 trigrams
  first token     from the moment the LLM request starts, i.e. AFE's ttftMs,
                  which excludes retrieval -- read from the turn log
                  (ttft_after_retrieval_ms), not the golden run's turn-start TTFT
  LLM total       likewise from the LLM request, so retrieval is subtracted
  by-type table   AFE's: mean / median / max first token, then means

Speech (--speech, from speech_bench.py) uses AFE's WER and TTS definitions.
Both apps' runs are warm (model resident, each prompt new), so they compare.
Needs openpyxl.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sheet import (  # noqa: E402
    AFE_FILL, BOLD, WARM_FILL, WRAP, Font, Workbook, fill_row, get_column_letter, load_afe,
    load_workbook, style_header,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "golden-comparison.xlsx"
AFE_RUNS = ROOT.parent / "AFE-Learning-App" / "dev-data" / "logs" / "benchmark"
TURNS_LOG = ROOT / "apps" / "backend" / "logs" / "turns.jsonl"
SHEET = "AFE vs this app"

FILLER = set(
    "a an and are as at be but by can for from has have in is it its of on or that the their them "
    "then there these they this to was were which with you your".split()
)
MIN_TRIGRAMS = 8
TYPES = ("short", "mid-size", "long", "follow-up")


def trigrams(text: str) -> set:
    grams = set()
    for word in re.findall(r"[^\W_]+", text.lower()):
        if word in FILLER or word.isdigit():
            continue
        if len(word) <= 3:
            grams.add(word)
            continue
        for i in range(len(word) - 2):
            grams.add(word[i : i + 3])
    return grams


def groundedness(answer: str, passages: List[str]) -> Optional[float]:
    if not passages:
        return None
    a = trigrams(answer)
    if len(a) < MIN_TRIGRAMS:
        return None
    p = trigrams(" ".join(passages))
    return round(sum(1 for g in a if g in p) / len(a), 3)


def coverage(points: List[List[str]], text: str) -> float:
    low = text.lower()
    return sum(any(alt.lower() in low for alt in alts) for alts in points) / len(points) if points else 0.0


def turn_log() -> Dict[str, Dict[str, Any]]:
    turns = {}
    if TURNS_LOG.exists():
        for line in TURNS_LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                t = json.loads(line)
                turns[t.get("turn_id")] = t
    return turns


def score_poc(run_dir: Path, golden: Dict[str, Dict[str, Any]], turns) -> Dict[str, Dict[str, Any]]:
    out = {}
    for r in json.loads((run_dir / "results.json").read_text()):
        passages = [c.get("excerpt") or "" for c in r.get("chunks", []) if c.get("sent", True) and c.get("excerpt")]
        t = turns.get(r["turn_id"], {})
        llm = t.get("llm", {})
        retrieval_ms = r.get("retrieval_ms") or 0
        points = golden[r["id"]]["points"]
        out[r["id"]] = {
            "ttft": llm.get("ttft_after_retrieval_ms") or (r["ttft_ms"] - retrieval_ms),
            "total": (llm.get("total_ms") or r["total_ms"]) - retrieval_ms,
            "retrieval": retrieval_ms,
            "prefill": r["prefill_ms"],
            "decode": r["decode_ms"],
            "tps": r["tokens_per_second"],
            "prompt_tok": r["prompt_tokens"],
            "out_tok": r["output_tokens"],
            "grounded": groundedness(r["answer"], passages),
            "ans": coverage(points, r["answer"]),
            "ctx": coverage(points, " ".join(passages)),
            "sources": ", ".join(dict.fromkeys(c["title"] for c in r.get("chunks", []) if c.get("sent", True))),
            "answer": r["answer"],
        }
    return out


def score_afe(afe: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        qid: {
            "ttft": a["llm"]["ttftMs"],
            "total": a["llm"]["totalMs"],
            "retrieval": a["retrieval"]["ms"],
            "prefill": a["llm"]["prefillMs"],
            "decode": a["llm"]["decodeMs"],
            "tps": a["llm"]["tokensPerSecond"],
            "prompt_tok": a["llm"]["promptTokens"],
            "out_tok": a["llm"]["evalTokens"],
            "grounded": a.get("groundedness"),
            "ans": a["answerFactCoverage"],
            "ctx": a["retrieval"]["factCoverage"],
            "sources": ", ".join(a["retrieval"].get("titles", [])),
            "answer": a.get("answer", ""),
        }
        for qid, a in afe.items()
    }


def agg(rows: List[Dict[str, Any]]) -> List[Any]:
    def vals(k):
        return [r[k] for r in rows if isinstance(r.get(k), (int, float))]

    def m(k, nd=0):
        v = vals(k)
        return round(statistics.mean(v), nd) if v else None

    ttft = vals("ttft")
    return [
        len(rows), round(statistics.mean(ttft)) if ttft else None, round(statistics.median(ttft)) if ttft else None,
        round(max(ttft)) if ttft else None, m("total"), m("retrieval", 1), m("prefill"), m("decode"), m("tps", 1),
        m("prompt_tok"), m("out_tok"), m("grounded", 2), m("ans", 2), m("ctx", 2),
    ]


AGG_HEAD = ["app", "type", "n", "first token mean ms", "first token median", "first token max", "LLM total mean ms",
            "retrieval mean ms", "prefill mean ms", "decode mean ms", "tok/s", "prompt tok mean", "output tok mean",
            "groundedness mean", "answer facts mean", "context facts mean"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", required=True, help='"Label=path/to/<run>-warm" (repeatable)')
    ap.add_argument("--speech", help="speech_bench.py run dir")
    ap.add_argument("--afe", help="AFE benchmark run dir (default: newest)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    golden = {q["id"]: q for q in json.loads((ROOT / "docs" / "groundedness" / "afe-golden.json").read_text())["questions"]}
    afe_dir = Path(args.afe) if args.afe else sorted(p for p in AFE_RUNS.iterdir() if p.is_dir())[-1]
    afe_raw, _ = load_afe(afe_dir)
    afe_doc = json.loads((afe_dir / "results.json").read_text())
    turns = turn_log()
    apps = [("AFE-Learning-App", score_afe(afe_raw))]
    for spec in args.run:
        label, _, path = spec.partition("=")
        apps.append(("This repo: " + label, score_poc(Path(path), golden, turns)))

    out = Path(args.out)
    wb = load_workbook(out) if out.exists() else Workbook()
    if SHEET in wb.sheetnames:
        del wb[SHEET]
    ws = wb.create_sheet(SHEET, 1)
    ws["A1"] = "AFE-Learning-App vs this repo, scored by AFE's golden-set rules"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = ("Same 20 questions, same model (qwen3.5:2b-q4_K_M), same machine, both warm. AFE run: {}. "
                "Runs: {}.").format(afe_dir.name, "; ".join(s.partition("=")[2].rsplit("/", 1)[-1] for s in args.run))
    ws["A3"] = ("First token and LLM total are timed from the LLM request, as AFE times them (retrieval excluded). "
                "Groundedness is AFE's character-trigram wording overlap, not correctness. Facts are keyword checks.")

    r = 5
    for c, h in enumerate(AGG_HEAD, 1):
        ws.cell(row=r, column=c, value=h)
    style_header(ws, r, len(AGG_HEAD))
    for t in TYPES + ("ALL",):
        for name, rows in apps:
            sel = [v for q, v in rows.items() if t == "ALL" or golden[q]["type"] == t]
            r += 1
            for c, v in enumerate([name, t] + agg(sel), 1):
                ws.cell(row=r, column=c, value=v)
                if t == "ALL":
                    ws.cell(row=r, column=c).font = BOLD
            fill_row(ws, r, len(AGG_HEAD), AFE_FILL if name.startswith("AFE") else WARM_FILL)

    if args.speech:
        sp = json.loads((Path(args.speech) / "results.json").read_text())["summary"]
        a = afe_doc["summary"]
        r += 2
        head = ["app", "STT model", "STT WER mean", "words", "after stop mean ms", "after stop max ms",
                "TTS voice", "first sentence mean ms", "RTF mean", "RTF max"]
        for c, h in enumerate(head, 1):
            ws.cell(row=r, column=c, value=h)
        style_header(ws, r, len(head))
        rows = [
            ["AFE-Learning-App", a["stt"]["model"], round(a["stt"]["wer"], 3), a["stt"]["wordsTotal"],
             round(a["stt"]["afterStopMsMean"]), round(a["stt"]["afterStopMsMax"]), a["tts"]["voice"],
             round(a["tts"]["firstSentenceMsMean"]), round(a["tts"]["rtfMean"], 3), round(a["tts"]["rtfMax"], 3)],
            ["This repo", sp["stt_model"], sp["wer_mean"], sp["words"], round(sp["after_stop_ms_mean"]),
             round(sp["after_stop_ms_max"]), sp["tts_voice"], round(sp["first_sentence_ms_mean"]),
             sp["rtf_mean"], sp["rtf_max"]],
        ]
        for row in rows:
            r += 1
            for c, v in enumerate(row, 1):
                ws.cell(row=r, column=c, value=v)
            fill_row(ws, r, len(head), AFE_FILL if row[0].startswith("AFE") else WARM_FILL)

    r += 3
    keys = [("first token ms", "ttft"), ("prefill ms", "prefill"), ("decode ms", "decode"), ("prompt tok", "prompt_tok"),
            ("output tok", "out_tok"), ("groundedness", "grounded"), ("answer facts", "ans"), ("context facts", "ctx"),
            ("sources", "sources")]
    head = ["id", "type", "question"] + ["{} | {}".format(lbl, name.replace("This repo: ", "")) for lbl, _ in keys for name, _ in apps]
    head += ["answer | {}".format(name.replace("This repo: ", "")) for name, _ in apps] + ["expected"]
    head_row = r
    for c, h in enumerate(head, 1):
        ws.cell(row=r, column=c, value=h)
    style_header(ws, r, len(head))
    for qid, q in golden.items():
        r += 1
        values = [qid, q["type"], q["question"]]
        for _, k in keys:
            for _, rows in apps:
                v = rows.get(qid, {}).get(k)
                values.append(round(v, 2) if isinstance(v, float) else v)
        values += [rows.get(qid, {}).get("answer") for _, rows in apps] + [q["answerShouldMention"]]
        for c, v in enumerate(values, 1):
            ws.cell(row=r, column=c, value=v).alignment = WRAP
    ws.freeze_panes = ws.cell(row=head_row + 1, column=4)
    for col in range(1, len(head) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 13
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["C"].width = 40
    for col in range(len(head) - len(apps), len(head) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 50
    wb.save(out)
    print("Wrote '{}' to {}".format(SHEET, out))
    for t in ("ALL",):
        for name, rows in apps:
            print("  {:<28} {}".format(name, agg(list(rows.values()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
