"""Rebuild the library from PDFs on disk, without going through the upload page.

Ingestion has only ever been reachable through the setup page's upload, which is
fine for a user and awkward for a measurement: re-running the groundedness eval
after an ingestion change means rebuilding the corpus reproducibly, from the
same files, with one command.

    python3 scripts/eval/rebuild_corpus.py                       # the Class 6 book
    python3 scripts/eval/rebuild_corpus.py --db /tmp/ncert.db \\
        --book "data/PDF NCERT/Class09-Science:9:Science:NCERT Class 9 Science"
    python3 scripts/eval/rebuild_corpus.py --dry-run             # chunk, don't embed

The existing database is copied aside before anything is written, with a
timestamp, because a corpus takes minutes to rebuild and the previous one is the
only baseline a comparison has. The copy uses sqlite's own backup API rather
than a file copy: this database runs in WAL mode, and copying the .db file alone
silently leaves recent writes behind in the -wal -- which is exactly how a
shipped payload once ended up with 16 of 327 chunks.
"""

import argparse
import asyncio
import hashlib
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps" / "backend"))
# textbook_ingest is NOT added to sys.path: it comes from the installed
# distribution (pdf-textbook-extract, editable during development). A path
# insert here would sit AHEAD of that install and silently shadow it, so a
# library change under test would be measured against the wrong copy.

import textbook_ingest as ti                                     # noqa: E402
from app.config import settings                                  # noqa: E402
from app.services.ollama_client import client as ollama         # noqa: E402
from app.services.rag.embeddings import embed_documents          # noqa: E402
from app.services.rag.store import LibraryStore                  # noqa: E402

DEFAULT_BOOK = "data/PDF English/Class6_Sci_book.pdf:6:Science:General Science (Class 6)"


def parse_book(spec: str):
    """`path:grade:subject:title` -- title may contain colons, path may not."""
    path, grade, subject, title = spec.split(":", 3)
    return Path(path), int(grade), subject, title


def backup(db_path: Path) -> Path:
    """Copy the corpus aside using sqlite's backup API, WAL included."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = db_path.with_name("{}.{}.bak".format(db_path.name, stamp))
    source = sqlite3.connect(str(db_path))
    destination = sqlite3.connect(str(target))
    with destination:
        source.backup(destination)
    source.close()
    destination.close()
    return target


def sources_for(path: Path):
    if path.is_dir():
        files = sorted(path.glob("*.pdf"))
        if not files:
            raise SystemExit("No PDFs in {}".format(path))
        return [ti.Source(name=f.name, data=f.read_bytes()) for f in files]
    return [ti.Source(name=path.name, data=path.read_bytes())]


async def ingest_one(store, path, grade, subject, title, options, dry_run, breadcrumb):
    print("\n=== {}  (class {} {})".format(title, grade, subject), flush=True)
    sources = sources_for(path)
    print("  {} source file(s)".format(len(sources)), flush=True)

    started = time.time()
    try:
        result = ti.ingest(sources, options)
    except ti.UnusableBook as exc:
        print("  REJECTED ({}): {}".format(exc.code, exc.detail))
        if exc.hint:
            print("  hint: {}".format(exc.hint))
        return None

    print("  profile: furniture={} labels={} captions={} bullets={}".format(
        len(result.profile.furniture), len(result.profile.labels),
        result.profile.caption_style, sorted(result.profile.bullets)[:3]))
    for warning in result.warnings:
        print("  ! {}".format(warning))
    if result.skipped:
        print("  !! NOT INGESTED: {}".format(", ".join(result.skipped)))
    print("  {} pages -> {} chunks ({} tables, {} headings) in {:.1f}s".format(
        result.stats["pages"], len(result.chunks), result.stats["table_chunks"],
        result.stats["distinct_headings"], time.time() - started), flush=True)

    if dry_run:
        return result

    digest = hashlib.sha256(b"".join(s.data for s in sources)).hexdigest()
    existing = store.find_by_hash(digest)
    if existing:
        print("  already present as '{}' -- deleting it first".format(existing["title"]))
        store.delete_document(existing["id"])

    document_id = store.add_document(
        filename=path.name, title=title, grade=grade, subject=subject,
        sha256=digest, pages=result.stats["pages"],
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    crumbs = ["Class {}".format(grade), subject] if breadcrumb else None
    batch_size = max(1, settings.rag_embed_batch_size)
    done = 0
    started = time.time()
    try:
        for start in range(0, len(result.chunks), batch_size):
            batch = result.chunks[start:start + batch_size]
            vectors = await embed_documents([c.embedding_text(crumbs) for c in batch])
            store.add_chunks(document_id, grade, subject, list(zip(batch, vectors)))
            done += len(batch)
            print("\r  embedding {}/{}".format(done, len(result.chunks)), end="", flush=True)
    except Exception:
        # A half-embedded book retrieves from its first chapters only and looks
        # like a tutor that simply does not know the rest. Roll it back whole.
        store.delete_document(document_id)
        print("\n  FAILED -- rolled back")
        raise
    print("\r  embedded {} chunks in {:.0f}s".format(done, time.time() - started), flush=True)
    return result


async def main_async(args):
    # The Ollama HTTP client is normally started by the FastAPI lifespan; this
    # script runs outside the app, so it opens and closes the pool itself.
    if not args.dry_run:
        await ollama.startup()
    try:
        await _rebuild(args)
    finally:
        if not args.dry_run:
            await ollama.shutdown()


async def _rebuild(args):
    db_path = Path(args.db) if args.db else REPO / "apps" / "backend" / settings.rag_db_path
    print("corpus: {}".format(db_path))
    print("embeddings: {} ({} dims)".format(
        settings.rag_embedding_model, settings.rag_embedding_dims))
    print("breadcrumb: {} | chunk {} | overlap {}".format(
        settings.rag_embed_breadcrumb, settings.rag_chunk_chars,
        settings.rag_chunk_overlap_chars))
    # Which copy of the cleaner produced this corpus. Printed because the library
    # is developed in a sibling checkout: two working copies can exist at once,
    # and a run measured against the wrong one is indistinguishable from a result.
    print("cleaner: textbook_ingest {} from {}".format(
        getattr(ti, "__version__", "?"),
        Path(ti.__file__).resolve().parent.parent.parent))

    if db_path.exists() and not args.dry_run:
        saved = backup(db_path)
        print("backed up -> {}".format(saved.name))

    # With --fresh the new corpus is built in a SIBLING file and moved into
    # place only once every book has embedded. Deleting first looks equivalent
    # and is not: embedding takes minutes and can fail on a cold Ollama, and a
    # run that dies half way then leaves an empty database where the corpus
    # used to be -- which is exactly what happened the first time this script
    # was run, and cost the corpus until a backup was found.
    target = db_path
    if args.fresh and not args.dry_run:
        target = db_path.with_name(db_path.name + ".building")
        for suffix in ("", "-wal", "-shm"):
            stale = target.with_name(target.name + suffix)
            if stale.exists():
                stale.unlink()

    store = None
    if not args.dry_run:
        store = LibraryStore(str(target), settings.rag_embedding_dims,
                             settings.rag_embedding_model)
        store.open()

    options = ti.IngestOptions(
        chunk_chars=settings.rag_chunk_chars,
        overlap_chars=settings.rag_chunk_overlap_chars,
        filter_apparatus=settings.rag_filter_corpus,
        exercise_page_ratio=settings.rag_exercise_page_ratio,
    )

    total = 0
    for spec in args.book:
        path, grade, subject, title = parse_book(spec)
        if not path.exists():
            print("\n!! missing: {}".format(path))
            continue
        result = await ingest_one(store, path, grade, subject, title, options,
                                  args.dry_run, settings.rag_embed_breadcrumb)
        if result:
            total += len(result.chunks)

    if store:
        store.close()
        if target != db_path:
            # Swap in only now, with every chunk embedded. os.replace is atomic
            # within a filesystem, so a reader never sees a half-built corpus.
            import os
            for suffix in ("-wal", "-shm"):
                stale = db_path.with_name(db_path.name + suffix)
                if stale.exists():
                    stale.unlink()
            os.replace(str(target), str(db_path))
            print("swapped the new corpus into place")
        with sqlite3.connect(str(db_path)) as conn:
            docs = conn.execute("select count(*) from documents").fetchone()[0]
            chunks = conn.execute("select count(*) from chunks").fetchone()[0]
        print("\ncorpus now holds {} document(s), {} chunks".format(docs, chunks))
    else:
        print("\ndry run: {} chunks would be written".format(total))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", action="append", default=None,
                        metavar="PATH:GRADE:SUBJECT:TITLE",
                        help="repeatable; a PDF or a directory of chapter PDFs")
    parser.add_argument("--db", help="database to write (default: the app's)")
    parser.add_argument("--fresh", action="store_true",
                        help="delete the existing corpus after backing it up")
    parser.add_argument("--dry-run", action="store_true",
                        help="chunk and report, embed nothing, touch no database")
    args = parser.parse_args()
    if not args.book:
        args.book = [DEFAULT_BOOK]
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
