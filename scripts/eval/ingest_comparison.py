"""Old pipeline vs textbook-ingest, over every book we have.

The old rules were tuned against one MSCERT book and measured well on it. The
only way to know whether the library is better rather than merely different is
to run both over the same eight books and compare the numbers that predicted the
failures in the first place:

  furniture caught      0 on MSCERT and 1 per NCERT book was the bug. A running
                        header that is never detected labels a third of the
                        corpus.
  distinct headings     the most sensitive single indicator of heading quality.
                        56 on MSCERT against 324 on NCERT Class 9 said the
                        detector was finding noise, not topics.
  exercise pages        1 of 274 on NCERT Class 10, against 31 pages that were
                        dense enough and carried no recognised stem.
  broken words          1.0 per 1,000 on MSCERT, 16.1 on NCERT Class 9.
  answer phrases        the hard gate. A filter that deletes a gold answer is a
                        regression whatever else improved.

    python3 scripts/eval/ingest_comparison.py
    python3 scripts/eval/ingest_comparison.py --json out.json
"""

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "backend"))
# textbook_ingest is NOT added to sys.path: it comes from the installed
# distribution (pdf-textbook-extract, editable during development). A path
# insert here would sit AHEAD of that install and silently shadow it, so a
# library change under test would be measured against the wrong copy.

import textbook_ingest as ti                                    # noqa: E402
from textbook_ingest import fidelity as ti_fidelity             # noqa: E402
from textbook_ingest import repair as ti_repair                 # noqa: E402

BOOKS = [
    ("MSCERT Cl.6 Science", REPO / "data" / "PDF English", "Class6_Sci_book.pdf"),
    ("NCERT Cl.1 Maths", REPO / "data" / "PDF NCERT" / "Class01-Maths-MathMagic", None),
    ("NCERT Cl.5 EVS", REPO / "data" / "PDF NCERT" / "Class05-EVS-LookingAround", None),
    ("NCERT Cl.6 Science", REPO / "data" / "PDF NCERT" / "Class06-Science", None),
    ("NCERT Cl.8 Science", REPO / "data" / "PDF NCERT" / "Class08-Science", None),
    ("NCERT Cl.9 Science", REPO / "data" / "PDF NCERT" / "Class09-Science", None),
    ("NCERT Cl.9 English", REPO / "data" / "PDF NCERT" / "Class09-English-Beehive", None),
    ("NCERT Cl.10 Science", REPO / "data" / "PDF NCERT" / "Class10-Science", None),
]

_REAL_SHORT = ti_repair._REAL_SHORT
_SPLIT = re.compile(r"\b[a-zA-Z]{2,}\s([a-z]{1,2})\b")


def norm(text):
    return " ".join((text or "").replace("’", "'").split()).lower()


def answer_phrases():
    """Every phrase either evaluation set treats as the book's own answer."""
    phrases = []
    bench = REPO / "packaging" / "windows" / "benchmark.py"
    if bench.exists():
        match = re.search(r"^ANSWER_KEY = \{.*?^\}", bench.read_text(), re.S | re.M)
        if match:
            ns = {}
            exec(match.group(0), ns)  # noqa: S102 - our own source file
            phrases += [p for v in ns["ANSWER_KEY"].values() for p in v]
    evalset = REPO / "docs" / "groundedness" / "evalset.json"
    if evalset.exists():
        data = json.loads(evalset.read_text())
        items = data if isinstance(data, list) else data.get("items", [])
        for item in items:
            for key in ("gold_quote", "gold_quotes", "quote", "quotes"):
                value = item.get(key) if isinstance(item, dict) else None
                if isinstance(value, str):
                    phrases.append(value)
                elif isinstance(value, list):
                    phrases += value
    return sorted({norm(p) for p in phrases if len(norm(p)) > 12})


def split_rate(texts):
    joined = " ".join(texts)
    words = len(joined.split())
    hits = [m for m in _SPLIT.finditer(joined) if m.group(1) not in _REAL_SHORT]
    return round(1000 * len(hits) / max(1, words), 1)


def paths_for(directory, single):
    if single:
        return [str(directory / single)]
    return sorted(str(p) for p in directory.glob("*.pdf"))


# The baseline is the config as it shipped BEFORE 2026-09-21, pinned here
# rather than read from settings -- otherwise changing a default silently moves
# the "before" side of the comparison and the numbers stop meaning anything.
OLD_CHUNK_CHARS = 700
OLD_OVERLAP = 105
OLD_RATIO = 0.40


def run_old(paths):
    """The pipeline as it shipped, at its own settings."""
    from app.services.rag import pdf_text as P
    from app.services.rag.chunking import chunk_pages
    from app.services.rag.quality import exercise_density, page_is_exercise

    raw = []
    skipped = 0
    for path in paths:
        try:
            raw += P.extract_pages(Path(path).read_bytes())
        except Exception:
            skipped += 1
    if not raw:
        return {"failed": "no pages", "skipped": skipped}

    normalised = [P._normalise_characters(p) for p in raw]
    furniture = P._find_repeated_lines(normalised)
    cleaned = P.clean_pages(raw)
    chunks = chunk_pages(cleaned, OLD_CHUNK_CHARS, OLD_OVERLAP, True, OLD_RATIO)
    paras = [[p for p in pg.split("\n\n") if p.strip()] for pg in cleaned]
    ex = sum(1 for pg in paras if pg and page_is_exercise(pg, OLD_RATIO))
    lens = [len(c.text) for c in chunks] or [0]
    return {
        "pages": len(raw),
        "skipped": skipped,
        "furniture": len(furniture),
        "chunks": len(chunks),
        "median_chunk": int(statistics.median(lens)),
        "headings": len({c.heading for c in chunks if c.heading}),
        "exercise_pages": ex,
        "splits_per_1k": split_rate([c.text for c in chunks]),
        "texts": [norm(c.text) for c in chunks],
        "top_headings": Counter(c.heading for c in chunks).most_common(3),
        "page1_citations": sum(1 for c in chunks if c.page_start == 1),
    }


def run_new(paths):
    try:
        result = ti.ingest_paths(paths)
    except ti.UnusableBook as exc:
        return {"rejected": exc.detail, "code": exc.code, "hint": exc.hint}
    lens = [len(c.text) for c in result.chunks] or [0]
    return {
        "pages": result.stats["pages"],
        "skipped": result.stats["skipped_sources"],
        "furniture": len(result.profile.furniture),
        "furniture_list": sorted(result.profile.furniture)[:3],
        "chunks": len(result.chunks),
        "median_chunk": int(statistics.median(lens)),
        "headings": result.stats["distinct_headings"],
        "exercise_pages": result.stats["exercise_pages"],
        "tables": result.stats["table_chunks"],
        "splits_per_1k": split_rate([c.text for c in result.chunks]),
        "texts": [norm(c.text) for c in result.chunks],
        "top_headings": Counter(c.heading for c in result.chunks).most_common(3),
        "labels": len(result.profile.labels),
        "caption_style": result.profile.caption_style,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="write the full comparison here")
    args = ap.parse_args()

    phrases = answer_phrases()
    print("{} gold answer phrases\n".format(len(phrases)))

    rows = []
    for label, directory, single in BOOKS:
        if not directory.exists():
            continue
        paths = paths_for(directory, single)
        if not paths:
            continue
        print("--- {} ({} file{})".format(label, len(paths), "" if len(paths) == 1 else "s"), flush=True)
        old = run_old(paths)
        new = run_new(paths)

        for side, data in (("old", old), ("new", new)):
            if "texts" in data:
                data["phrases_found"] = sum(
                    1 for p in phrases if any(p in t for t in data["texts"])
                )
                del data["texts"]
        rows.append({"book": label, "old": old, "new": new})
        print("    old: {}".format({k: v for k, v in old.items() if k != "top_headings"}), flush=True)
        print("    new: {}".format({k: v for k, v in new.items() if k != "top_headings"}), flush=True)

    print("\n" + "=" * 100)
    print("{:<22}{:>9}{:>9}{:>11}{:>11}{:>11}{:>11}".format(
        "book", "furn old", "furn new", "heads old", "heads new", "splits old", "splits new"))
    print("=" * 100)
    for row in rows:
        o, n = row["old"], row["new"]
        if "rejected" in n:
            print("{:<22}{:>9}{:>9}   REJECTED: {}".format(
                row["book"], o.get("furniture", "-"), "-", n["code"]))
            continue
        print("{:<22}{:>9}{:>9}{:>11}{:>11}{:>11}{:>11}".format(
            row["book"], o.get("furniture", "-"), n["furniture"],
            o.get("headings", "-"), n["headings"],
            o.get("splits_per_1k", "-"), n["splits_per_1k"]))

    print("\nANSWER-PHRASE SAFETY (MSCERT book is the only one with a gold set)")
    for row in rows:
        o, n = row["old"], row["new"]
        if "phrases_found" in o and "phrases_found" in n:
            flag = "OK " if n["phrases_found"] >= o["phrases_found"] else "REGRESSION"
            print("  {:<22} old {:>3}/{}   new {:>3}/{}   {}".format(
                row["book"], o["phrases_found"], len(phrases),
                n["phrases_found"], len(phrases), flag))

    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        print("\nwrote", args.json)


if __name__ == "__main__":
    main()
