"""Command line entry point: look at what a book turns into before indexing it.

    textbook-ingest data/PDF\\ NCERT/Class09-Science
    textbook-ingest book.pdf --chunks 5
    textbook-ingest a_directory --profile-only
    textbook-ingest a_directory --json out.json

Exists because the expensive mistake is discovering a bad corpus after it has
been embedded. Printing the profile alone takes a few seconds and says whether
the running header was found, which is the single thing most likely to be wrong
on a book the library has not seen.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .errors import UnusableBook
from .pipeline import IngestOptions, ingest_paths


def _paths(target: str):
    path = Path(target)
    if path.is_dir():
        found = sorted(str(p) for p in path.glob("*.pdf"))
        if not found:
            raise SystemExit("No PDFs in {}".format(target))
        return found
    if not path.exists():
        raise SystemExit("No such file: {}".format(target))
    return [str(path)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="textbook-ingest",
        description="Turn a textbook PDF (or a directory of chapter PDFs) into chunks.",
    )
    parser.add_argument("target", help="a PDF, or a directory of chapter PDFs")
    parser.add_argument("--chunks", type=int, default=3, metavar="N",
                        help="print the first N chunks in full (default 3)")
    parser.add_argument("--profile-only", action="store_true",
                        help="print what was learned about the book and stop")
    parser.add_argument("--chunk-chars", type=int, default=700)
    parser.add_argument("--overlap", type=int, default=0)
    parser.add_argument("--no-filter", action="store_true",
                        help="keep exercises and activity boxes")
    parser.add_argument("--no-repair", action="store_true",
                        help="skip the text-repair pass")
    parser.add_argument("--force", action="store_true",
                        help="ingest even if the text looks unreadable")
    parser.add_argument("--json", metavar="FILE", help="write chunks and stats here")
    args = parser.parse_args(argv)

    options = IngestOptions(
        chunk_chars=args.chunk_chars,
        overlap_chars=args.overlap,
        filter_apparatus=not args.no_filter,
        repair_text=not args.no_repair,
        enforce_fidelity=not args.force,
    )

    try:
        result = ingest_paths(_paths(args.target), options)
    except UnusableBook as exc:
        print("REJECTED: {}".format(exc.detail), file=sys.stderr)
        if exc.hint:
            print("  {}".format(exc.hint), file=sys.stderr)
        print("  (--force ingests it anyway)", file=sys.stderr)
        return 2

    profile = result.profile
    print("PROFILE")
    print("  furniture      {}".format(sorted(profile.furniture) or "-- none found --"))
    print("  caption style  {}".format(profile.caption_style))
    print("  bullets        {}".format(sorted(profile.bullets) or "--"))
    if profile.space_substitute:
        print("  space glyph    U+{:04X}".format(ord(profile.space_substitute)))
    print("  labels         {} learned, e.g. {}".format(
        len(profile.labels), sorted(profile.labels)[:6]))

    print("\nSTATS")
    for key in ("pages", "paragraphs", "chunks", "chunks_per_page",
                "distinct_headings", "table_chunks", "skipped_sources"):
        if key in result.stats:
            print("  {:<18} {}".format(key, result.stats[key]))

    if result.warnings:
        print("\nWARNINGS ({})".format(len(result.warnings)))
        for warning in result.warnings[:10]:
            print("  ! {}".format(warning))
        if len(result.warnings) > 10:
            print("  ... {} more".format(len(result.warnings) - 10))

    if result.skipped:
        print("\nSKIPPED SOURCES -- these chapters are NOT in the corpus")
        for name in result.skipped:
            print("  x {}".format(name))

    if args.profile_only:
        return 0

    headings = Counter(c.heading for c in result.chunks if c.heading)
    print("\nTOP BREADCRUMB HEADINGS")
    for heading, count in headings.most_common(8):
        print("  {:>4}  {!r}".format(count, heading))

    if args.chunks:
        print("\nFIRST {} CHUNKS".format(args.chunks))
        for chunk in result.chunks[:args.chunks]:
            print("\n  [{}] pages {}-{} ({}) {} chars  heading={!r}".format(
                chunk.ordinal, chunk.page_start, chunk.page_end,
                chunk.kind, len(chunk.text), chunk.heading))
            for line in chunk.text.splitlines():
                print("     {}".format(line))

    if args.json:
        Path(args.json).write_text(json.dumps({
            "stats": result.stats,
            "profile": profile.as_dict(),
            "warnings": [str(w) for w in result.warnings],
            "skipped": result.skipped,
            "chunks": [
                {
                    "ordinal": c.ordinal, "text": c.text, "heading": c.heading,
                    "page_start": c.page_start, "page_end": c.page_end,
                    "source": c.source, "kind": c.kind,
                }
                for c in result.chunks
            ],
        }, indent=1, ensure_ascii=False))
        print("\nwrote {}".format(args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
