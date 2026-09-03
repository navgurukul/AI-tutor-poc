"""Store-level tests: the three indexes have to stay in step.

Every failure mode here is silent -- a stale FTS row keeps matching a passage
that no longer exists, and a missing one just makes the lexical leg quietly
useless -- so these assert on the tables directly rather than through search.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.rag.store import LibraryStore, vector_table_for  # noqa: E402


DIMS = 8


class _Chunk:
    def __init__(self, ordinal, text, heading=""):
        self.ordinal = ordinal
        self.text = text
        self.heading = heading
        self.page_start = 1
        self.page_end = 1


@pytest.fixture
def store(tmp_path):
    s = LibraryStore(
        db_path=str(tmp_path / "library.db"), dims=DIMS, embedding_model="bge-m3"
    )
    s.open()
    yield s
    s.close()


def _vec(seed: float):
    return [seed] * DIMS


def _add_book(store, *, grade=9, subject="Science", language="en", texts=None):
    doc_id = store.add_document(
        filename="book.pdf",
        title="Science",
        grade=grade,
        subject=subject,
        sha256="hash-{}-{}".format(grade, language),
        pages=1,
        created_at="2026-01-01T00:00:00+00:00",
        language=language,
    )
    texts = texts or ["A tissue is a group of cells with a common origin."]
    store.add_chunks(
        doc_id,
        grade,
        subject,
        [(_Chunk(i, t), _vec(0.1 * (i + 1))) for i, t in enumerate(texts)],
        language,
    )
    return doc_id


def test_table_is_named_for_its_model():
    assert vector_table_for("bge-m3") == "chunk_vectors_bge_m3"
    assert vector_table_for("nomic-embed-text") == "chunk_vectors_nomic_embed_text"


def test_meta_records_the_active_table(store):
    conn = store._require()
    meta = dict(conn.execute("select key, value from meta").fetchall())
    assert meta["schema_version"] == "3"
    assert meta["embedding_model"] == "bge-m3"
    assert meta["embedding_dims"] == str(DIMS)
    assert meta["vector_table"] == "chunk_vectors_bge_m3"


def test_delete_removes_chunks_vectors_and_fts_rows(store):
    """The check the verification list asks for: nothing survives a delete."""
    doc_id = _add_book(store)
    conn = store._require()

    assert conn.execute("select count(*) from chunks").fetchone()[0] == 1
    assert conn.execute(
        "select count(*) from chunk_vectors_bge_m3"
    ).fetchone()[0] == 1
    assert conn.execute(
        "select count(*) from chunks_fts where chunks_fts match '\"tissue\"'"
    ).fetchone()[0] == 1

    assert store.delete_document(doc_id) is True

    assert conn.execute("select count(*) from chunks").fetchone()[0] == 0
    assert conn.execute(
        "select count(*) from chunk_vectors_bge_m3"
    ).fetchone()[0] == 0
    assert conn.execute(
        "select count(*) from chunks_fts where chunks_fts match '\"tissue\"'"
    ).fetchone()[0] == 0
    assert conn.execute("select count(*) from documents").fetchone()[0] == 0


def test_fts_indexes_devanagari_through_trigram(store):
    """unicode61 shatters conjuncts; trigram is why the lexical leg works at all."""
    _add_book(store, language="hi", texts=["ऊतक कोशिकाओं का समूह है जो कार्य करता है।"])
    hits = store.search_lexical('"कार्य"', grade=9, k=10)
    assert len(hits) == 1
    assert "ऊतक" in hits[0].text


def test_lexical_leg_respects_grade(store):
    """FTS5 has no partition key, so the grade filter is a join that must hold."""
    _add_book(store, grade=6, texts=["A tissue in the Class 6 book."])
    _add_book(store, grade=9, texts=["A tissue in the Class 9 book."])

    six = store.search_lexical('"tissue"', grade=6, k=10)
    assert len(six) == 1 and "Class 6" in six[0].text

    nine = store.search_lexical('"tissue"', grade=9, k=10)
    assert len(nine) == 1 and "Class 9" in nine[0].text

    both = store.search_lexical('"tissue"', grade=None, k=10)
    assert len(both) == 2


def test_language_is_metadata_not_a_partition(store):
    """A Hindi question has to be able to reach an English page."""
    _add_book(store, language="en", texts=["Tissues are groups of cells."])
    conn = store._require()
    cols = [
        r[1] for r in conn.execute("pragma table_info(chunk_vectors_bge_m3)").fetchall()
    ]
    assert "language" in cols
    hits = store.search(_vec(0.1), grade=9, subject=None, k=5)
    assert hits and hits[0].language == "en"


def test_neighbours_are_same_document_only(store):
    doc_id = _add_book(store, texts=["First chunk.", "Second chunk.", "Third chunk."])
    conn = store._require()
    ids = [r[0] for r in conn.execute(
        "select id from chunks where document_id = ? order by ordinal", (doc_id,)
    ).fetchall()]
    assert set(store.neighbours(ids[1])) == {ids[0], ids[2]}
    assert store.neighbours(ids[0]) == [ids[1]]


def test_stale_fts_rows_are_detectable_if_the_delete_is_skipped(store):
    """Why delete_document has to remove FTS rows explicitly.

    chunks_fts is external-content, so nothing cascades into it. Skipping the
    delete leaves an index that still satisfies MATCH but whose rows cannot be
    read -- a citation to a passage the student no longer has. This asserts the
    failure mode directly, so that if delete_document ever stops removing FTS
    rows the reason is on the record.
    """
    _add_book(store)
    conn = store._require()
    conn.execute("delete from chunks")  # content only; index untouched

    stale = conn.execute(
        "select count(*) from chunks_fts where chunks_fts match '\"tissue\"'"
    ).fetchone()[0]
    assert stale == 1, "expected the index to outlive the content"
    with pytest.raises(Exception, match="missing row"):
        conn.execute(
            "select text from chunks_fts where chunks_fts match '\"tissue\"'"
        ).fetchone()


def test_delete_needs_the_original_text_not_just_the_rowid(store):
    """The real hazard: FTS5's delete command trusts the values it is given.

    It does not re-read chunks.text, so the order of the two statements is
    immaterial -- ordering the delete before or after the content row makes no
    difference, and the plan was wrong to say otherwise. What matters is the
    *values*: given the wrong text, FTS5 decrements postings for terms the row
    never had, which leaves the index both stale and structurally damaged.

    delete_document selects id and text together, before deleting anything,
    for exactly this reason.
    """
    _add_book(store)
    conn = store._require()
    row = conn.execute("select id, text from chunks").fetchone()

    conn.execute(
        "insert into chunks_fts(chunks_fts, rowid, text) values ('delete', ?, ?)",
        (row[0], "entirely the wrong text"),
    )
    # Still matching -- the passage was never actually removed from the index.
    assert conn.execute(
        "select count(*) from chunks_fts where chunks_fts match '\"tissue\"'"
    ).fetchone()[0] == 1

    # And the damage is not recoverable by then doing it correctly.
    with pytest.raises(Exception):
        conn.execute(
            "insert into chunks_fts(chunks_fts, rowid, text) values ('delete', ?, ?)",
            (row[0], row[1]),
        )
        conn.execute(
            "select count(*) from chunks_fts where chunks_fts match '\"tissue\"'"
        ).fetchone()
