"""What ingest-time filtering would remove from a textbook, before you ingest it.

`app.services.rag.quality` deletes text from the corpus, and deleted text cannot
be recovered by any later stage -- a passage that is not in the index can never
be retrieved, and the tutor then answers from the model alone and sounds fine
doing it. So the filter has to be shown to be safe on the book in hand, not
assumed safe because it was safe on another one.

    python3 scripts/eval/corpus_filter_report.py
    python3 scripts/eval/corpus_filter_report.py "data/PDF English/Class6_Sci_book.pdf"
    python3 scripts/eval/corpus_filter_report.py --ratio 0.5 --show-dropped 40

It prints three things:

  THE SAFETY CHECK      every answer phrase from both evaluation sets
                        (packaging/windows/benchmark.py's ANSWER_KEY and
                        docs/groundedness/evalset.json's gold quotes) looked for
                        in the corpus before and after filtering. A phrase that
                        survives extraction but not filtering is a regression,
                        and the exit code is non-zero so CI can catch it.

  THE PAGE TABLE        exercise density per page, sorted. The threshold should
                        sit in a gap in this list rather than on a slope; on the
                        Class 6 book the answer pages measure 0.00-0.08 and the
                        exercise pages 0.40-1.02, which is why 0.40 is the
                        default and why it is safe to be approximate.

  WHAT WOULD GO         a sample of the dropped paragraphs, to read.

Nothing is written and no database is touched.
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "apps" / "backend"
sys.path.insert(0, str(BACKEND))

from app.services.rag import pdf_text                       # noqa: E402
from app.services.rag.chunking import chunk_pages           # noqa: E402
from app.services.rag.quality import (                      # noqa: E402
    clean_heading,
    exercise_density,
    keep_on_exercise_page,
    page_is_exercise,
    strip_apparatus,
)

DEFAULT_PDF = REPO / "data" / "PDF English" / "Class6_Sci_book.pdf"
EVALSET = REPO / "docs" / "groundedness" / "evalset.json"
BENCHMARK = REPO / "packaging" / "windows" / "benchmark.py"


def norm(text):
    text = (text or "").replace("’", "'").replace("‘", "'")
    return " ".join(text.split()).lower()


def answer_phrases():
    """Every phrase either evaluation set treats as the book's own answer.

    Two sets rather than one because they cover different chapters: benchmark.py
    keys 20 questions, the groundedness set 12 more with full quotes. A filter
    safe on one and not the other is not safe.
    """
    phrases = []
    if BENCHMARK.exists():
        match = re.search(r"^ANSWER_KEY = \{.*?^\}", BENCHMARK.read_text(), re.S | re.M)
        if match:
            namespace = {}
            exec(match.group(0), namespace)  # noqa: S102 - our own source file
            phrases += [p for v in namespace["ANSWER_KEY"].values() for p in v]
    if EVALSET.exists():
        data = json.loads(EVALSET.read_text())
        phrases += [
            e["quote"] for item in data["items"] for e in item.get("gold_evidence") or []
        ]
    return sorted(set(phrases))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", nargs="?", default=str(DEFAULT_PDF))
    ap.add_argument("--ratio", type=float, default=0.40,
                    help="exercise-page threshold to report on (default 0.40)")
    ap.add_argument("--show-dropped", type=int, default=25)
    ap.add_argument("--show-pages", type=int, default=20)
    args = ap.parse_args(argv)

    pdf = Path(args.pdf)
    if not pdf.exists():
        print("no such PDF: {}".format(pdf))
        return 2

    print("reading {} ...".format(pdf.name))
    pages, raw_count = pdf_text.extract_and_clean(pdf.read_bytes())
    print("  {} pages\n".format(raw_count))

    per_page = [[p.strip() for p in page.split("\n\n") if p.strip()] for page in pages]
    dropped_pages, kept_paras, dropped_paras, samples = [], 0, [], []
    for number, paragraphs in enumerate(per_page, start=1):
        if not paragraphs:
            continue
        if page_is_exercise(paragraphs, args.ratio):
            dropped_pages.append(number)
            kept = keep_on_exercise_page(paragraphs)
            why = "exercise page"
        else:
            kept = strip_apparatus(paragraphs)
            why = "apparatus"
        kept_paras += len(kept)
        # keep_on_exercise_page rewrites a line (it strips the bullet), so what
        # survived is matched on normalised text rather than identity.
        survived = {" ".join(k.split()) for k in kept}
        for p in paragraphs:
            flat = " ".join(p.split())
            if flat not in survived and flat.lstrip("l\u2022\u25cf\u00b7 ").strip() not in survived:
                dropped_paras.append(p)
                samples.append((number, p, why))

    total = kept_paras + len(dropped_paras)

    # ---- the safety check ------------------------------------------------
    raw = norm(" ".join(pages))
    filtered = norm(" ".join(
        " ".join(keep_on_exercise_page(paras) if n + 1 in dropped_pages
                 else strip_apparatus(paras))
        for n, paras in enumerate(per_page)
    ))
    phrases = answer_phrases()
    present = [p for p in phrases if norm(p) in raw]
    lost = [p for p in present if norm(p) not in filtered]
    never = [p for p in phrases if norm(p) not in raw]

    print("=" * 78)
    print("SAFETY CHECK -- answer phrases from both evaluation sets")
    print("=" * 78)
    print("  {} phrases, {} present in the extracted text".format(len(phrases), len(present)))
    if never:
        print("  {} never extracted at all (a chunking or extraction issue, not this "
              "filter):".format(len(never)))
        for p in never[:5]:
            print("      - {}".format(p[:70]))
    if lost:
        print("\n  !! {} ANSWER PHRASE(S) LOST BY FILTERING:".format(len(lost)))
        for p in lost:
            print("      - {}".format(p[:74]))
    else:
        print("\n  OK: every answer phrase that survives extraction also survives filtering.")

    # ---- the page table --------------------------------------------------
    print("\n" + "=" * 78)
    print("EXERCISE DENSITY PER PAGE (threshold {:.2f})".format(args.ratio))
    print("=" * 78)
    scored = sorted(
        ((n, exercise_density(p), len(p)) for n, p in enumerate(per_page, 1) if p),
        key=lambda r: -r[1],
    )
    print("  {:<6} {:<8} {:<7} {}".format("page", "density", "paras", ""))
    for number, density, count in scored[:args.show_pages]:
        mark = "DROPPED" if number in dropped_pages else ""
        print("  {:<6} {:<8.2f} {:<7} {}".format(number, density, count, mark))
    if len(scored) > args.show_pages:
        print("  ... {} more pages, all below {:.2f}".format(
            len(scored) - args.show_pages, scored[args.show_pages][1]))

    # ---- chunk-level effect ----------------------------------------------
    before = chunk_pages(pages, 1200, 180, drop_exercises=False)
    after = chunk_pages(pages, 1200, 180, drop_exercises=True,
                        exercise_page_ratio=args.ratio)
    headings_before = sum(1 for c in before if c.heading)
    headings_after = sum(1 for c in after if c.heading)

    print("\n" + "=" * 78)
    print("EFFECT")
    print("=" * 78)
    print("  exercise pages, kept for their summary only: {} ({})".format(
        len(dropped_pages), ", ".join(str(p) for p in dropped_pages) or "none"))
    print("  paragraphs {} -> {} ({:.1f}% dropped)".format(
        total, kept_paras, 100 * len(dropped_paras) / total if total else 0))
    print("  chunks     {} -> {}".format(len(before), len(after)))
    print("  chunks with a heading in the breadcrumb: {} -> {}".format(
        headings_before, headings_after))
    tiny_before = sum(1 for c in before if len(c.text) < 200)
    tiny_after = sum(1 for c in after if len(c.text) < 200)
    print("  chunks under 200 chars: {} ({:.0%}) -> {} ({:.0%})".format(
        tiny_before, tiny_before / max(len(before), 1),
        tiny_after, tiny_after / max(len(after), 1)))

    # ---- what would go ---------------------------------------------------
    print("\n" + "=" * 78)
    print("WHAT WOULD BE REMOVED (sample of {})".format(len(dropped_paras)))
    print("=" * 78)
    step = max(1, len(samples) // max(args.show_dropped, 1))
    for number, para, why in samples[::step][:args.show_dropped]:
        print("  p.{:<4} [{}] {}".format(number, why, " ".join(para.split())[:96]))

    print("\n" + ("FAILED: filtering removes answer text." if lost
                  else "Filtering looks safe on this book."))
    return 1 if lost else 0


if __name__ == "__main__":
    raise SystemExit(main())
