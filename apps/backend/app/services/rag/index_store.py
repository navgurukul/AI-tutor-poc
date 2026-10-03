"""rag-engine/src/store.ts, with sqlite-vec in place of the HNSW file.

Same tables and the same BM25 query as AFE; the dense side is an exact
cosine search (vec0) where AFE uses an approximate HNSW graph. Exact is the
upper bound of what HNSW finds, so any difference is HNSW missing something,
and at 2,274 chunks the exact scan costs about a millisecond.
"""

import json
import logging
import re
import sqlite3
import struct
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.services.rag.models import Chunk, SectionInfo

logger = logging.getLogger(__name__)


class StoreUnavailable(Exception):
    """The index cannot be used. Carries a message for /health and a fix for the operator."""

    def __init__(self, detail: str, hint: Optional[str] = None):
        super().__init__(detail)
        self.detail = detail
        self.hint = hint


def _serialise(vector: Sequence[float]) -> bytes:
    """sqlite-vec takes float32 vectors as a raw little-endian blob."""
    return struct.pack("<{}f".format(len(vector)), *vector)


_COLUMNS = "id, doc_id, seq, text, metadata_json, chapter_title, topic_title, subtopic_title"


def open_connection(path: Path, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect("file:{}?mode=ro".format(path), uri=True, check_same_thread=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class IndexStore:
    def __init__(self, path: str, dims: int, embedding_model: str):
        self.path = Path(path)
        self.dims = dims
        self.embedding_model = embedding_model
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._sections: Optional[List[SectionInfo]] = None
        self.unavailable_reason: Optional[StoreUnavailable] = None

    # -- lifecycle ---------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def open(self, create: bool = False) -> None:
        if not create and not self.path.exists():
            raise StoreUnavailable(
                "Textbook index not found at {}.".format(self.path),
                hint="Build it: apps/backend/.venv/bin/python scripts/eval/ingest_afe_corpus.py",
            )
        try:
            import sqlite_vec
        except ImportError as exc:
            raise StoreUnavailable("sqlite-vec is not installed.") from exc
        conn = open_connection(self.path)
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except Exception as exc:  # noqa: BLE001
            conn.close()
            raise StoreUnavailable("Failed to load sqlite-vec: {}".format(exc)) from exc
        self._conn = conn
        self._create_tables()
        self._check_or_stamp_meta()
        logger.info(
            "Textbook index ready at %s (%d chunks, %d dims, model=%s)",
            self.path, self.chunk_count(), self.dims, self.embedding_model,
        )

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StoreUnavailable("Textbook index is not open.")
        return self._conn

    def _create_tables(self) -> None:
        conn = self._db()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS documents (
              id TEXT PRIMARY KEY, title TEXT, source TEXT, metadata_json TEXT
            );
            CREATE TABLE IF NOT EXISTS chunks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
              seq INTEGER NOT NULL,
              text TEXT NOT NULL,
              metadata_json TEXT,
              chapter_id INTEGER, chapter_title TEXT,
              topic_id INTEGER, topic_title TEXT,
              subtopic_id INTEGER, subtopic_title TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_chapter ON chunks(doc_id, chapter_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_topic ON chunks(doc_id, topic_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_subtopic ON chunks(doc_id, subtopic_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
              text, content='chunks', content_rowid='id'
            );
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
              INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
            END;
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
              INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
            END;
            """
        )
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec USING vec0("
            "chunk_id integer primary key, embedding float[{}] distance_metric=cosine)".format(self.dims)
        )
        conn.commit()

    def _check_or_stamp_meta(self) -> None:
        """Vectors from two embedding models cannot be compared; refuse to mix."""
        conn = self._db()
        rows = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        expected = {"embedding_model": self.embedding_model, "embedding_dims": str(self.dims)}
        if not rows:
            conn.executemany("INSERT INTO meta(key, value) VALUES (?, ?)", list(expected.items()))
            conn.commit()
            return
        for key, want in expected.items():
            if rows.get(key) not in (None, want):
                raise StoreUnavailable(
                    "Textbook index at {} was built with {}={!r}, but this backend expects {!r}.".format(
                        self.path, key, rows[key], want
                    ),
                    hint="Rebuild it with scripts/eval/ingest_afe_corpus.py.",
                )

    # -- writes (ingest) ---------------------------------------------------
    def add_document(self, doc_id: str, title: Optional[str], source: Optional[str], metadata_json: str) -> None:
        with self._lock:
            self._db().execute(
                "INSERT OR REPLACE INTO documents (id, title, source, metadata_json) VALUES (?, ?, ?, ?)",
                (doc_id, title, source, metadata_json),
            )

    def add_chunk(self, row: Dict[str, Any], vector: Sequence[float]) -> None:
        """Insert one chunk under its original id, with its vector."""
        with self._lock:
            conn = self._db()
            conn.execute(
                "INSERT INTO chunks (id, doc_id, seq, text, metadata_json, chapter_id, chapter_title,"
                " topic_id, topic_title, subtopic_id, subtopic_title)"
                " VALUES (:id, :doc_id, :seq, :text, :metadata_json, :chapter_id, :chapter_title,"
                " :topic_id, :topic_title, :subtopic_id, :subtopic_title)",
                row,
            )
            conn.execute(
                "INSERT INTO chunk_vec (chunk_id, embedding) VALUES (?, ?)",
                (row["id"], _serialise(vector)),
            )

    def commit(self) -> None:
        with self._lock:
            self._db().commit()

    # -- reads -------------------------------------------------------------
    def document_count(self) -> int:
        return self._db().execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def chunk_count(self) -> int:
        return self._db().execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    @staticmethod
    def _to_chunk(r: sqlite3.Row) -> Chunk:
        metadata = json.loads(r["metadata_json"] or "{}")
        metadata.update(
            {
                "chapterTitle": r["chapter_title"] or None,
                "topicTitle": r["topic_title"] or None,
                "subtopicTitle": r["subtopic_title"] or None,
            }
        )
        return Chunk(id=r["id"], doc_id=r["doc_id"], seq=r["seq"], text=r["text"], metadata=metadata)

    def get_chunks_by_ids(self, ids: Sequence[int]) -> List[Chunk]:
        """In the caller's order -- the caller passes ids in fused-rank order."""
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        with self._lock:
            rows = self._db().execute(
                "SELECT {} FROM chunks WHERE id IN ({})".format(_COLUMNS, marks), list(ids)
            ).fetchall()
        by_id = {r["id"]: self._to_chunk(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def get_chunks_by_seqs(self, doc_id: str, seqs: Sequence[int]) -> List[Chunk]:
        if not seqs:
            return []
        marks = ",".join("?" * len(seqs))
        with self._lock:
            rows = self._db().execute(
                "SELECT {} FROM chunks WHERE doc_id = ? AND seq IN ({}) ORDER BY seq".format(_COLUMNS, marks),
                [doc_id, *seqs],
            ).fetchall()
        return [self._to_chunk(r) for r in rows]

    def get_chunks_by_section(self, doc_id: str, level: str, section_id: int) -> List[Chunk]:
        column = {"chapter": "chapter_id", "topic": "topic_id", "subtopic": "subtopic_id"}[level]
        with self._lock:
            rows = self._db().execute(
                "SELECT {} FROM chunks WHERE doc_id = ? AND {} = ? ORDER BY seq".format(_COLUMNS, column),
                (doc_id, section_id),
            ).fetchall()
        return [self._to_chunk(r) for r in rows]

    def list_sections(self) -> List[SectionInfo]:
        """Every distinct chapter/topic/subtopic across documents. Cached: the
        index only changes by being rebuilt, which restarts the backend."""
        if self._sections is not None:
            return self._sections
        with self._lock:
            rows = self._db().execute(
                "SELECT DISTINCT doc_id, chapter_id, chapter_title, topic_id, topic_title,"
                " subtopic_id, subtopic_title FROM chunks"
                " WHERE chapter_id IS NOT NULL OR topic_id IS NOT NULL OR subtopic_id IS NOT NULL"
            ).fetchall()
        sections: List[SectionInfo] = []
        seen = set()

        def add(doc_id: str, level: str, section_id: int, title: str) -> None:
            key = (doc_id, level, section_id)
            if key not in seen:
                seen.add(key)
                sections.append(SectionInfo(doc_id, level, section_id, title))

        for r in rows:
            if r["chapter_id"] is not None:
                add(r["doc_id"], "chapter", r["chapter_id"], r["chapter_title"])
            if r["topic_id"] is not None:
                add(r["doc_id"], "topic", r["topic_id"], r["topic_title"])
            if r["subtopic_id"] is not None:
                add(r["doc_id"], "subtopic", r["subtopic_id"], r["subtopic_title"])
        self._sections = sections
        return sections

    def lexical_search(self, query: str, k: int) -> List[int]:
        """BM25, best first. Same OR-of-prefix-terms query as AFE's store.ts."""
        terms = [t + "*" for t in re.sub(r'["*^]', " ", query).split() if t]
        if not terms:
            return []
        try:
            with self._lock:
                rows = self._db().execute(
                    "SELECT rowid AS id, bm25(chunks_fts) AS rank FROM chunks_fts"
                    " WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                    (" OR ".join(terms), k),
                ).fetchall()
            return [r["id"] for r in rows]
        except sqlite3.Error:
            # Malformed term (rare punctuation): no lexical matches, not a failed turn.
            return []

    def dense_search(self, vector: Sequence[float], k: int) -> List[Tuple[int, float]]:
        """(chunk id, cosine distance), nearest first."""
        with self._lock:
            rows = self._db().execute(
                "SELECT chunk_id, distance FROM chunk_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                (_serialise(vector), k),
            ).fetchall()
        return [(r["chunk_id"], r["distance"]) for r in rows]
