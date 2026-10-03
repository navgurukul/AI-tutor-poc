#!/usr/bin/env python3
"""Build this app's AFE-style index from AFE-Learning-App's own chunks.

Why copy chunks instead of re-reading the PDFs: AFE's chunking depends on how
pdf-parse breaks lines (its heading and section detection runs on them), and a
Python PDF reader breaks them differently, so a re-extraction would give
different chunks and the comparison would be about the chunker, not retrieval.
Reading AFE's index gives the identical 2,274 chunks, with their ids, sequence
numbers and chapter/topic/subtopic columns. What is done here, fresh, is the
embedding: every chunk is embedded with nomic-embed-text (768 dims, document
prefix), the model AFE's model-config.ts names.

    apps/backend/.venv/bin/python scripts/eval/ingest_afe_corpus.py
    apps/backend/.venv/bin/python scripts/eval/ingest_afe_corpus.py --source /path/to/rag-index.db


Needs Ollama running with the embedding model pulled (ollama pull nomic-embed-text).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "apps" / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # settings use paths relative to the backend

from app.config import settings  # noqa: E402
from app.services.ollama_client import client  # noqa: E402
from app.services.rag.index_store import IndexStore, open_connection  # noqa: E402
from app.services.rag.embeddings import embed_documents  # noqa: E402

DEFAULT_SOURCE = ROOT.parent / "AFE-Learning-App" / "dev-data" / "rag" / "rag-index.db"
BATCH = 16  # AFE's OllamaEmbedder batch size


async def build(source: Path, target: Path) -> int:
    src = open_connection(source, read_only=True)
    documents = src.execute("SELECT id, title, source, metadata_json FROM documents ORDER BY rowid").fetchall()
    chunks = src.execute(
        "SELECT id, doc_id, seq, text, metadata_json, chapter_id, chapter_title, topic_id, topic_title,"
        " subtopic_id, subtopic_title FROM chunks ORDER BY id"
    ).fetchall()
    print("Source: {} documents, {} chunks ({})".format(len(documents), len(chunks), source))

    for suffix in ("", "-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)
    store = IndexStore(str(target), dims=settings.rag_embedding_dims, embedding_model=settings.rag_embedding_model)
    store.open(create=True)
    for d in documents:
        store.add_document(d["id"], d["title"], d["source"], d["metadata_json"])

    await client.startup()
    started = time.perf_counter()
    try:
        for i in range(0, len(chunks), BATCH):
            batch = chunks[i : i + BATCH]
            vectors = await embed_documents([c["text"] for c in batch])
            for row, vector in zip(batch, vectors):
                store.add_chunk(dict(row), vector)
            if (i // BATCH) % 10 == 0 or i + BATCH >= len(chunks):
                done = min(i + BATCH, len(chunks))
                rate = done / (time.perf_counter() - started)
                print("  embedded {}/{} ({:.1f} chunks/s)".format(done, len(chunks), rate), flush=True)
        store.commit()
    finally:
        await client.shutdown()

    count = store.chunk_count()
    vectors_in = store._db().execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0]
    store.close()
    if count != len(chunks) or vectors_in != len(chunks):
        raise SystemExit("Count mismatch: {} chunks, {} vectors, expected {}".format(count, vectors_in, len(chunks)))
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(DEFAULT_SOURCE), help="AFE's rag-index.db")
    args = ap.parse_args()

    source = Path(args.source).expanduser()
    if not source.exists():
        print("Source index not found: {}".format(source), file=sys.stderr)
        return 1
    target = Path(settings.hybrid_index_path)
    building = target.with_name(target.name + ".building")

    count = asyncio.run(build(source, building))
    os.replace(building, target)
    for suffix in ("-wal", "-shm"):
        Path(str(building) + suffix).unlink(missing_ok=True)
    print("Built {} ({} chunks, model {}, {} dims)".format(target.resolve(), count, settings.rag_embedding_model, settings.rag_embedding_dims))

    return 0


if __name__ == "__main__":
    sys.exit(main())
