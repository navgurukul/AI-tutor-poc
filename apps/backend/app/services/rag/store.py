"""The textbook corpus: one SQLite file holding text, metadata and vectors.

Everything lives in a single file on purpose. On the target laptops -- 15W
dual-core EliteBooks at the low end -- embedding a corpus takes the better part
of a working day, so the index is built once on a fast machine and the .db file
is copied onto each device. A single file is what makes that a copy rather than
a deployment.

sqlite-vec supplies the `vec0` virtual table. Grade is a partition key and
subject a metadata column, so a Class 6 question searches only Class 6 vectors
instead of ranking the whole library and filtering afterwards -- which would
quietly return fewer than k results whenever the nearest neighbours belong to
another grade.
"""

import logging
import re
import sqlite3
import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 3


def vector_table_for(model: str) -> str:
    """The vec0 table name for an embedding model.

    Naming the table after the model is what makes the choice reversible. A
    re-embed job can fill `chunk_vectors_bge_m3` in the background while
    `chunk_vectors_nomic_embed_text` goes on serving queries, and the cutover
    is a `meta` update rather than a migration on every device. Retrofitting
    the name after an index has shipped is not.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")
    return "chunk_vectors_{}".format(slug or "unknown")


class StoreUnavailable(Exception):
    """Raised when the vector store cannot be opened.

    Carries a hint because the most likely cause is fixable but not guessable:
    a Python built without SQLite extension support cannot load sqlite-vec at
    all, and macOS's system Python 3.9 is exactly such a build.
    """

    def __init__(self, detail: str, hint: Optional[str] = None):
        super().__init__(detail)
        self.detail = detail
        self.hint = hint


@dataclass
class Retrieved:
    chunk_id: int
    text: str
    heading: str
    page_start: int
    page_end: int
    distance: float
    document_title: str
    grade: int
    subject: str
    language: str = ""


def _serialise(vector: Sequence[float]) -> bytes:
    """sqlite-vec takes float32 vectors as a raw little-endian blob."""
    return struct.pack("<{}f".format(len(vector)), *vector)


class LibraryStore:
    def __init__(self, db_path: str, dims: int, embedding_model: str):
        self.db_path = Path(db_path)
        self.dims = dims
        self.embedding_model = embedding_model
        # Named for the model it holds, so a re-embed can build the next one
        # alongside it instead of over it.
        self.vector_table = vector_table_for(embedding_model)
        self._conn: Optional[sqlite3.Connection] = None
        # One connection guarded by a lock. SQLite handles concurrent readers
        # fine, but ingestion writes in bulk from a worker thread while chat
        # reads, and a single serialised connection is simpler to reason about
        # than a pool for a corpus this size.
        self._lock = threading.Lock()
        self.unavailable_reason: Optional[StoreUnavailable] = None

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> None:
        try:
            import sqlite_vec
        except ImportError as exc:
            raise StoreUnavailable(
                "sqlite-vec is not installed.",
                hint="Run: pip install -r requirements.txt",
            ) from exc

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        if not hasattr(conn, "enable_load_extension"):
            conn.close()
            raise StoreUnavailable(
                "This Python build cannot load SQLite extensions, which sqlite-vec needs.",
                hint=(
                    "macOS's system Python 3.9 is built without extension support. "
                    "Install Python 3.11+ (Windows: `winget install Python.Python.3.12`) "
                    "and recreate apps/backend/.venv with it."
                ),
            )
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except Exception as exc:
            conn.close()
            raise StoreUnavailable(
                "Failed to load the sqlite-vec extension: {}".format(exc),
                hint="Confirm the sqlite-vec wheel matches this Python and platform.",
            ) from exc

        self._conn = conn
        self._migrate()
        logger.info(
            "Library store ready at %s (%d dims, model=%s, %d documents)",
            self.db_path,
            self.dims,
            self.embedding_model,
            self.document_count(),
        )

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def _require(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StoreUnavailable(
                "The textbook library is not available.",
                hint=self.unavailable_reason.hint if self.unavailable_reason else None,
            )
        return self._conn

    # -- schema ------------------------------------------------------------
    def _migrate(self) -> None:
        conn = self._require()
        with self._lock, conn:
            conn.execute("pragma foreign_keys = on")
            # WAL lets a chat request read while an ingestion writes.
            conn.execute("pragma journal_mode = wal")
            conn.executescript(
                """
                create table if not exists meta (
                    key text primary key,
                    value text not null
                );
                create table if not exists documents (
                    id integer primary key autoincrement,
                    filename text not null,
                    title text not null,
                    grade integer not null,
                    subject text not null,
                    language text not null default '',
                    sha256 text not null unique,
                    pages integer not null,
                    chunk_count integer not null default 0,
                    created_at text not null
                );
                create table if not exists chunks (
                    id integer primary key autoincrement,
                    document_id integer not null
                        references documents(id) on delete cascade,
                    ordinal integer not null,
                    page_start integer not null,
                    page_end integer not null,
                    heading text not null default '',
                    text text not null
                );
                create index if not exists idx_chunks_document on chunks(document_id);
                """
            )
            # Full-text index over the same rows, in the same file. `trigram`
            # rather than the default unicode61: unicode61 shatters Devanagari
            # conjuncts -- कार्य becomes क, र, य -- which is useless for BM25.
            # Trigram indexes every script the same way.
            #
            # external content (content='chunks'), so the text is stored once.
            # That is why delete_document() has to remove the index rows by
            # hand, and before the content rows go.
            conn.execute(
                """create virtual table if not exists chunks_fts using fts5(
                       text,
                       content='chunks',
                       content_rowid='id',
                       tokenize='trigram'
                   )"""
            )
            # Cosine, not the vec0 default of L2. nomic's vectors are not unit
            # length, so an L2 distance mixes "different topic" with "longer
            # passage" and the cut-off stops meaning anything. Cosine compares
            # direction only, which is what the model was trained for and what
            # makes rag_max_distance portable across models.
            #
            # `language` is a metadata column, deliberately not a second
            # partition key: grade x language x subject would shard the table
            # into fragments too small to be worth scanning separately, and a
            # Hindi question has to reach an English page anyway.
            conn.execute(
                """create virtual table if not exists {} using vec0(
                       chunk_id integer primary key,
                       grade integer partition key,
                       subject text,
                       language text,
                       embedding float[{}] distance_metric=cosine
                   )""".format(self.vector_table, self.dims)
            )
            self._check_or_stamp_meta(conn)

    def _check_or_stamp_meta(self, conn: sqlite3.Connection) -> None:
        """Refuse to mix embeddings from two different models.

        The vector width is fixed when the vec0 table is created, so a smaller
        model would fail loudly -- but another 768-dim model would insert
        happily and silently return nonsense, because distances between vectors
        from different models are meaningless. The stamp turns that into an
        error at startup.
        """
        rows = dict(conn.execute("select key, value from meta").fetchall())
        expected = {
            "schema_version": str(SCHEMA_VERSION),
            "embedding_model": self.embedding_model,
            "embedding_dims": str(self.dims),
            "vector_table": self.vector_table,
        }
        if not rows:
            conn.executemany(
                "insert into meta(key, value) values (?, ?)", list(expected.items())
            )
            return
        for key, want in expected.items():
            got = rows.get(key)
            if got is not None and got != want:
                raise StoreUnavailable(
                    "Library at {} was built with {}={!r}, but this backend expects {!r}.".format(
                        self.db_path, key, got, want
                    ),
                    hint=(
                        "Delete the file to rebuild it, or set the matching value in .env. "
                        "Vectors from different models cannot be compared."
                    ),
                )

    # -- reads -------------------------------------------------------------
    def document_count(self) -> int:
        conn = self._require()
        with self._lock:
            return conn.execute("select count(*) from documents").fetchone()[0]

    def chunk_count(self) -> int:
        conn = self._require()
        with self._lock:
            return conn.execute("select count(*) from chunks").fetchone()[0]

    def list_documents(self) -> List[Dict[str, Any]]:
        conn = self._require()
        with self._lock:
            rows = conn.execute(
                """select id, filename, title, grade, subject, pages,
                          chunk_count, created_at
                   from documents order by grade, subject, title"""
            ).fetchall()
        return [dict(r) for r in rows]

    def find_by_hash(self, sha256: str) -> Optional[Dict[str, Any]]:
        conn = self._require()
        with self._lock:
            row = conn.execute(
                "select id, title, grade, subject from documents where sha256 = ?",
                (sha256,),
            ).fetchone()
        return dict(row) if row else None

    def coverage(self) -> List[Dict[str, Any]]:
        """Which (grade, subject) pairs actually have content behind them."""
        conn = self._require()
        with self._lock:
            rows = conn.execute(
                """select grade, subject, language, count(*) as documents,
                          coalesce(sum(chunk_count), 0) as chunks
                   from documents group by grade, subject, language
                   order by grade, subject, language"""
            ).fetchall()
        return [dict(r) for r in rows]

    # -- writes ------------------------------------------------------------
    def add_document(
        self,
        *,
        filename: str,
        title: str,
        grade: int,
        subject: str,
        sha256: str,
        pages: int,
        created_at: str,
        language: str = "",
    ) -> int:
        conn = self._require()
        with self._lock, conn:
            cursor = conn.execute(
                """insert into documents
                       (filename, title, grade, subject, language, sha256, pages,
                        created_at)
                   values (?, ?, ?, ?, ?, ?, ?, ?)""",
                (filename, title, grade, subject, language, sha256, pages, created_at),
            )
        return int(cursor.lastrowid)

    def add_chunks(
        self,
        document_id: int,
        grade: int,
        subject: str,
        records: Iterable[Tuple[Any, Sequence[float]]],
        language: str = "",
    ) -> int:
        """Insert chunks, their vectors and their full-text rows together.

        All three are written inside one transaction: a chunk row with no
        vector is invisible to dense search, a vector with no chunk row would
        surface as a result with no text, and a chunk missing from chunks_fts
        is invisible to the lexical leg -- each of which fails silently, as a
        quietly worse answer rather than an error.
        """
        conn = self._require()
        written = 0
        with self._lock, conn:
            for chunk, vector in records:
                cursor = conn.execute(
                    """insert into chunks
                           (document_id, ordinal, page_start, page_end, heading, text)
                       values (?, ?, ?, ?, ?, ?)""",
                    (
                        document_id,
                        chunk.ordinal,
                        chunk.page_start,
                        chunk.page_end,
                        chunk.heading,
                        chunk.text,
                    ),
                )
                chunk_id = int(cursor.lastrowid)
                conn.execute(
                    """insert into {}(chunk_id, grade, subject, language, embedding)
                       values (?, ?, ?, ?, ?)""".format(self.vector_table),
                    (chunk_id, grade, subject, language, _serialise(vector)),
                )
                # External-content FTS5: the rowid has to match chunks.id, and
                # the row has to be inserted explicitly -- there is no trigger.
                conn.execute(
                    "insert into chunks_fts(rowid, text) values (?, ?)",
                    (chunk_id, chunk.text),
                )
                written += 1
            conn.execute(
                "update documents set chunk_count = chunk_count + ? where id = ?",
                (written, document_id),
            )
        return written

    def delete_document(self, document_id: int) -> bool:
        """Remove a document, its chunks, its vectors and its full-text rows.

        Two indexes here take no part in a foreign-key cascade and each needs
        removing by hand, in a specific order:

        vec0 tables ignore foreign keys entirely, so stale vectors would go on
        matching queries with no text to show for them.

        chunks_fts is an external-content table: it stores the index but not
        the text. Its `delete` command takes the original column values and
        uses them to work out which terms to remove -- it does not read them
        back out of `chunks`. So what matters is not the order of the two
        statements but that the *correct original text* is passed, which is
        why the select below fetches `text` alongside `id` and why it runs
        before anything is deleted.

        Get that wrong -- pass the wrong text, or skip the delete -- and the
        index keeps matching a passage that no longer exists. Measured: the
        stale row still satisfies MATCH, and reading it fails with "fts5:
        missing row from content table". The student sees a citation to a
        book that is gone.
        """
        conn = self._require()
        with self._lock, conn:
            rows = conn.execute(
                "select id, text from chunks where document_id = ?", (document_id,)
            ).fetchall()
            if rows:
                conn.executemany(
                    "delete from {} where chunk_id = ?".format(self.vector_table),
                    [(r[0],) for r in rows],
                )
                # The exact text the row was indexed with. See the docstring.
                conn.executemany(
                    "insert into chunks_fts(chunks_fts, rowid, text) "
                    "values ('delete', ?, ?)",
                    [(r[0], r[1]) for r in rows],
                )
            conn.execute("delete from chunks where document_id = ?", (document_id,))
            cursor = conn.execute("delete from documents where id = ?", (document_id,))
        return cursor.rowcount > 0

    # -- re-embedding ------------------------------------------------------
    def chunks_for_reembedding(self) -> List[Dict[str, Any]]:
        """Every chunk, with the breadcrumbed text it should be embedded as.

        The breadcrumb is rebuilt here rather than stored, so a re-embed
        reproduces exactly what ingestion would have produced -- if the
        breadcrumb format ever changes, the next re-embed picks it up.
        """
        conn = self._require()
        with self._lock:
            rows = conn.execute(
                """select c.id, c.text, c.heading, d.grade, d.subject, d.language
                   from chunks c join documents d on d.id = c.document_id
                   order by c.id"""
            ).fetchall()
        out = []
        for r in rows:
            crumbs = ["Class {}".format(r["grade"]), r["subject"]]
            if r["heading"]:
                crumbs.append(r["heading"])
            out.append(
                {
                    "chunk_id": r["id"],
                    "grade": r["grade"],
                    "subject": r["subject"],
                    "language": r["language"] or "",
                    "embedding_text": "{}\n\n{}".format(" > ".join(crumbs), r["text"]),
                }
            )
        return out

    def create_vector_table(self, table: str, dims: int) -> None:
        conn = self._require()
        with self._lock, conn:
            conn.execute(
                """create virtual table if not exists {} using vec0(
                       chunk_id integer primary key,
                       grade integer partition key,
                       subject text,
                       language text,
                       embedding float[{}] distance_metric=cosine
                   )""".format(table, dims)
            )

    def fill_vector_table(
        self, table: str, rows: Sequence[Dict[str, Any]], vectors: Sequence[Sequence[float]]
    ) -> int:
        conn = self._require()
        with self._lock, conn:
            for row, vector in zip(rows, vectors):
                conn.execute(
                    """insert into {}(chunk_id, grade, subject, language, embedding)
                       values (?, ?, ?, ?, ?)""".format(table),
                    (
                        row["chunk_id"],
                        row["grade"],
                        row["subject"],
                        row["language"],
                        _serialise(vector),
                    ),
                )
        return len(rows)

    def drop_vector_table(self, table: str) -> None:
        """Abandon a half-built table. Never called on the active one."""
        if table == self.vector_table:
            raise ValueError("Refusing to drop the table currently serving queries.")
        conn = self._require()
        with self._lock, conn:
            conn.execute("drop table if exists {}".format(table))

    def activate_vector_table(self, table: str, model: str, dims: int) -> None:
        """Cut over to a freshly built table, in one transaction.

        Until this runs, queries have been served from the old table and the
        new one has been invisible. After it, the reverse -- with no window in
        which the tutor is reading a table that is half full.
        """
        conn = self._require()
        previous = self.vector_table
        with self._lock, conn:
            conn.executemany(
                "insert into meta(key, value) values (?, ?) "
                "on conflict(key) do update set value = excluded.value",
                [
                    ("embedding_model", model),
                    ("embedding_dims", str(dims)),
                    ("vector_table", table),
                ],
            )
            if previous != table:
                conn.execute("drop table if exists {}".format(previous))
        self.vector_table = table
        self.embedding_model = model
        self.dims = dims
        logger.info("Vector table cut over: %s -> %s (%s)", previous, table, model)

    # -- search ------------------------------------------------------------
    def search(
        self,
        embedding: Sequence[float],
        *,
        grade: Optional[int],
        subject: Optional[str],
        k: int,
        max_distance: Optional[float] = None,
    ) -> List[Retrieved]:
        """k nearest chunks, restricted to a grade and subject when given.

        The KNN runs in a CTE and the text is joined on afterwards: vec0 wants
        its MATCH query kept simple, and joining inside it is what produces
        "unable to use function MATCH in the requested context".
        """
        conn = self._require()
        filters = ["v.embedding match ?", "k = ?"]
        params: List[Any] = [_serialise(embedding), k]
        if grade is not None:
            filters.append("v.grade = ?")
            params.append(grade)
        if subject:
            filters.append("v.subject = ?")
            params.append(subject)

        sql = """
            with knn as (
                select chunk_id, distance
                from {table} v
                where {filters}
            )
            select knn.chunk_id, knn.distance, c.text, c.heading,
                   c.page_start, c.page_end, d.title, d.grade, d.subject,
                   d.language
            from knn
            join chunks c on c.id = knn.chunk_id
            join documents d on d.id = c.document_id
            order by knn.distance
        """.format(table=self.vector_table, filters=" and ".join(filters))

        with self._lock:
            rows = conn.execute(sql, params).fetchall()

        hits = [
            Retrieved(
                chunk_id=r["chunk_id"],
                text=r["text"],
                heading=r["heading"],
                page_start=r["page_start"],
                page_end=r["page_end"],
                distance=float(r["distance"]),
                document_title=r["title"],
                grade=r["grade"],
                subject=r["subject"],
                language=r["language"] or "",
            )
            for r in rows
        ]
        if max_distance is not None:
            hits = [h for h in hits if h.distance <= max_distance]
        return hits

    def search_lexical(
        self,
        match_query: str,
        *,
        grade: Optional[int],
        k: int,
    ) -> List[Retrieved]:
        """Best BM25 matches for an already-built FTS5 MATCH string.

        The grade filter is a join, not a partition: FTS5 has no partition key,
        so without this a Class 6 question can pull a Class 9 passage into the
        fusion and out the other side with a citation on it. The dense leg gets
        that for free from vec0; this leg has to ask.

        `distance` is left at 1.0 -- BM25 scores are not distances and the two
        are never compared. Fusion is by rank precisely so they need no common
        scale.
        """
        if not match_query.strip():
            return []
        conn = self._require()
        params: List[Any] = [match_query]
        where = ["chunks_fts match ?"]
        if grade is not None:
            where.append("d.grade = ?")
            params.append(grade)
        params.append(k)

        sql = """
            select c.id as chunk_id, c.text, c.heading, c.page_start, c.page_end,
                   d.title, d.grade, d.subject, d.language
            from chunks_fts
            join chunks c on c.id = chunks_fts.rowid
            join documents d on d.id = c.document_id
            where {}
            order by bm25(chunks_fts)
            limit ?
        """.format(" and ".join(where))

        with self._lock:
            rows = conn.execute(sql, params).fetchall()
        return [
            Retrieved(
                chunk_id=r["chunk_id"],
                text=r["text"],
                heading=r["heading"],
                page_start=r["page_start"],
                page_end=r["page_end"],
                distance=1.0,
                document_title=r["title"],
                grade=r["grade"],
                subject=r["subject"],
                language=r["language"] or "",
            )
            for r in rows
        ]

    def neighbours(self, chunk_id: int, ordinals: int = 1) -> List[int]:
        """Chunk ids immediately either side of one, in the same document.

        Used by the gate: a definition split across a chunk boundary should
        stay retrievable through the half that cleared the gate, without
        letting an unrelated lexical hit ride in on a good one.
        """
        conn = self._require()
        with self._lock:
            row = conn.execute(
                "select document_id, ordinal from chunks where id = ?", (chunk_id,)
            ).fetchone()
            if row is None:
                return []
            rows = conn.execute(
                """select id from chunks
                   where document_id = ? and ordinal between ? and ?
                     and id != ?""",
                (row["document_id"], row["ordinal"] - ordinals,
                 row["ordinal"] + ordinals, chunk_id),
            ).fetchall()
        return [r[0] for r in rows]
