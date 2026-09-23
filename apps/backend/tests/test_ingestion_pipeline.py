"""The structural ingestion pipeline, on PDFs built to break it.

Every test here corresponds to a defect measured on the live Class X Geography
library on 2026-09-20, before the pipeline was ported (see EXP-019):

    42% of chunks carried a paragraph break mid-sentence  -> two-column tests
    35% carried a useless breadcrumb (book title, MCQ option) -> section tests
    83% were larger than the prompt could carry           -> sizing tests
    3% of exercises were tagged as such                   -> exercise tests

The PDFs are synthesised with PyMuPDF rather than checked in, so the geometry
that each test depends on is visible in the test itself. A fixture PDF would
hide exactly the thing under test.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pymupdf = pytest.importorskip("pymupdf")

from app.config import settings  # noqa: E402
from app.services.rag import ingestion  # noqa: E402
from app.services.rag.ingestion import layout  # noqa: E402
from app.services.rag.query import estimate_tokens  # noqa: E402
from app.services.rag.retrieval import is_exercise, trim_passage  # noqa: E402
from app.services.rag.store import Retrieved  # noqa: E402

A4 = (595, 842)

# Column geometry of a typical NCERT page: text 60..535 with a gutter at ~297.
LEFT_X, RIGHT_X = 60, 310


def _page(doc):
    return doc.new_page(width=A4[0], height=A4[1])


def _two_column_pdf(left_lines, right_lines, *, heading="Black Soil", tail=()):
    """A page with a heading, two columns, and optional full-width tail lines."""
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_text((LEFT_X, 70), heading, fontsize=18, fontname="hebo")
    y = 110
    for left, right in zip(left_lines, right_lines):
        page.insert_text((LEFT_X, y), left, fontsize=11)
        page.insert_text((RIGHT_X, y), right, fontsize=11)
        y += 18
    y = 320
    for line in tail:
        size, name = (14, "hebo") if line.endswith(":") else (11, "helv")
        page.insert_text((LEFT_X, y), line.rstrip(":"), fontsize=size, fontname=name)
        y += 22
    data = doc.tobytes()
    doc.close()
    return data


LEFT = [
    "These soils are black in colour",
    "and are also called regur soils.",
    "Black soil is considered ideal for",
    "growing cotton and is known as",
    "black cotton soil everywhere.",
    "Climate and parent rock matter.",
]
RIGHT = [
    "These soils are found in the north",
    "west Deccan plateau region and",
    "are made from lava rocks. They",
    "occur in Maharashtra, Saurashtra,",
    "Malwa and Madhya Pradesh too.",
    "Tilling begins with the monsoon.",
]


# -- two columns -----------------------------------------------------------

def test_gutter_is_found_between_two_columns():
    document, report = ingestion.analyze(_two_column_pdf(LEFT, RIGHT), {})
    assert report["layout"]["two_column"] == 1
    assert document.pages[0].column_count == 2


def test_columns_are_not_interleaved_into_one_paragraph():
    """The defect: a left-column line glued to the right-column line beside it.

    PyMuPDF returns both as lines of ONE block, so without the split the chunk
    reads "These soils are black in colour These soils are found in the north
    and are also called regur soils. west Deccan plateau region and ..." --
    fluent nonsense that embeds as nonsense.
    """
    chunks, _ = ingestion.build_chunks(_two_column_pdf(LEFT, RIGHT), {})
    body = " ".join(c.text for c in chunks)

    # Each column's own sentences survive intact...
    assert "black in colour and are also called regur soils" in body
    assert "lava rocks. They occur in Maharashtra, Saurashtra," in body
    # ...and no left-column line runs straight into a right-column one.
    assert "black in colour These soils are found" not in body
    assert "regur soils. west Deccan" not in body


def test_full_width_line_does_not_mask_the_gutter():
    """A spanning line lays ink across the gap and hides it from the projection.

    Excluded from the projection by `_MAX_BOX_WIDTH_RATIO`; without that, one
    exercise line at the foot of the page turns a two-column page back into a
    single-column one and the interleaving returns.
    """
    tail = (
        "Exercises:",
        "1. In which of these states is black soil mainly found?",
        "(a) Punjab   (b) Haryana   (c) Maharashtra   (d) Jharkhand",
    )
    document, report = ingestion.analyze(_two_column_pdf(LEFT, RIGHT, tail=tail), {})
    assert report["layout"]["two_column"] == 1, "full-width tail masked the gutter"
    assert document.pages[0].column_count == 2


def test_single_column_page_is_left_alone():
    doc = pymupdf.open()
    page = _page(doc)
    y = 100
    for line in LEFT + RIGHT:
        page.insert_text((LEFT_X, y), line, fontsize=11)
        y += 18
    data = doc.tobytes()
    doc.close()

    document, report = ingestion.analyze(data, {})
    assert report["layout"]["two_column"] == 0
    assert document.pages[0].column_count == 1


def test_content_below_the_columns_is_read_after_both_of_them():
    """Reading order: "Exercises" must not come before the right column.

    It did, because anything left of the gutter was treated as more of column
    0 regardless of how far down the page it sat. `chunk.add_exercise` then
    absorbed the entire right-hand column into the exercise -- six paragraphs
    of the lesson indexed as a question.
    """
    tail = (
        "Exercises:",
        "1. In which of these states is black soil mainly found?",
        "(a) Punjab   (b) Haryana   (c) Maharashtra   (d) Jharkhand",
    )
    chunks, _ = ingestion.build_chunks(_two_column_pdf(LEFT, RIGHT, tail=tail), {})

    prose = " ".join(c.text for c in chunks if c.content_type != "exercise")
    exercises = " ".join(c.text for c in chunks if c.content_type == "exercise")

    assert "Maharashtra, Saurashtra" in prose, "right column was swallowed"
    assert "Maharashtra, Saurashtra" not in exercises


def _prose_column_pdf():
    """Two columns of real running prose, wrapped across many lines.

    The lines wrap mid-sentence, as printed prose does. That is the case the
    first version of the splitter got wrong and the short fixtures above could
    not catch: with one line per block there is nothing for `join_soft_wraps`
    to rejoin, so every line fragment became a "sentence" and every chunk broke
    where the printed LINE broke rather than where the sentence did.
    """
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_text((LEFT_X, 70), "Soil Types", fontsize=18, fontname="hebo")
    left = [
        "Red soil develops on crystalline igneous",
        "rock and is found across the eastern and",
        "southern Deccan plateau region of India.",
        "The red colour comes from the diffusion",
        "of iron in the crystalline rocks below it.",
        "It looks yellow when it is hydrated well.",
    ]
    right = [
        "Black soil is black in colour and these",
        "soils are also called regur soils by many.",
        "Black soil is considered ideal for growing",
        "cotton and is known as black cotton soil.",
        "These soils occur in Maharashtra and in",
        "Saurashtra, Malwa and Madhya Pradesh.",
    ]
    y = 110
    for a, b in zip(left, right):
        page.insert_text((LEFT_X, y), a, fontsize=11)
        page.insert_text((RIGHT_X, y), b, fontsize=11)
        y += 15          # tight leading: one paragraph, not six
    data = doc.tobytes()
    doc.close()
    return data


def test_wrapped_lines_are_rejoined_into_prose():
    """A column's lines must arrive as one block, or nothing downstream works."""
    document, _ = ingestion.analyze(_prose_column_pdf(), {})
    page = document.pages[0]
    bodies = [b for b in page.text_blocks if "Red soil" in b.normalized_text
              or "Black soil" in b.normalized_text]

    assert bodies, "the columns vanished"
    for block in bodies:
        assert len(block.lines) > 1, (
            "each column is one block per LINE -- join_soft_wraps has nothing "
            "to rejoin and every fragment becomes a sentence"
        )


def test_no_chunk_ends_mid_sentence():
    """The defect that made the re-ingested library unanswerable.

    Every chunk in the first re-ingest stopped wherever the printed line
    stopped: "...इनका पीला रंग इनमें जलयोजन के कारण होता है। काली मृदा". The
    model cannot answer from a passage that breaks off, and the sentence
    overlap then carried the fragment into the next chunk too.
    """
    chunks, _ = ingestion.build_chunks(_prose_column_pdf(), {})
    assert chunks

    terminators = (".", "!", "?", "।", "॥", ":")
    for chunk in chunks:
        if chunk.content_type != "paragraph":
            continue
        assert chunk.text.rstrip().endswith(terminators), (
            "chunk ends mid-sentence: ...%r" % chunk.text[-60:]
        )


def test_a_sentence_split_across_printed_lines_survives_whole():
    chunks, _ = ingestion.build_chunks(_prose_column_pdf(), {})
    body = " ".join(c.text for c in chunks)

    # Each of these is printed across two lines and must come back joined.
    assert "Red soil develops on crystalline igneous rock" in body
    assert "These soils occur in Maharashtra and in Saurashtra, Malwa and Madhya Pradesh." in body


# -- exercises -------------------------------------------------------------

def test_multiple_choice_options_are_tagged_as_an_exercise():
    """Three wrong answers beside one right one, with nothing marking which.

    The worst possible thing to hand a model as a factual source: asked where
    black soil is found, a tutor given this block answered "Punjab, Haryana,
    Uttar Pradesh" and displayed "100% grounded".
    """
    tail = (
        "Exercises:",
        "1. In which of these states is black soil mainly found?",
        "(a) Punjab   (b) Haryana   (c) Maharashtra   (d) Jharkhand",
    )
    chunks, _ = ingestion.build_chunks(_two_column_pdf(LEFT, RIGHT, tail=tail), {})
    options = [c for c in chunks if "(a) Punjab" in c.text]

    assert options, "the option block was dropped entirely"
    assert all(c.content_type == "exercise" for c in options)


def test_explanatory_prose_is_not_tagged_as_an_exercise():
    """Over-tagging costs a passage; this is the guard against it."""
    chunks, _ = ingestion.build_chunks(_two_column_pdf(LEFT, RIGHT), {})
    assert chunks
    assert all(c.content_type != "exercise" for c in chunks)


def test_stored_content_type_beats_the_text_heuristic():
    """`is_exercise` prefers the classifier; the regex is only the fallback.

    The text below is what the heuristic is good at: an instruction plus
    lettered parts, which it calls an exercise on the words alone. The point
    of the test is that when the CLASSIFIER has looked at the same block's
    geometry and called it prose, the classifier wins -- because lettered
    parts are also how a chapter enumerates the thing it is explaining, and
    only the page's layout can tell those apart.
    """
    from app.services.rag.retrieval import looks_like_exercise

    text = (
        "निम्नलिखित प्रश्नों के उत्तर लिखिए। (क) उत्पत्ति के आधार पर (ख) समाप्यता "
        "के आधार पर (ग) स्वामित्व के आधार पर (घ) विकास के आधार पर।"
    )
    assert looks_like_exercise(text) is True, "fixture no longer exercises the fallback"

    def hit(content_type):
        return Retrieved(
            chunk_id=1, text=text, heading="", page_start=1, page_end=1,
            distance=0.4, document_title="t", grade=10, subject="Geography",
            content_type=content_type,
        )

    # Stored type wins in BOTH directions -- this is the precedence under test.
    assert is_exercise(hit("paragraph")) is False
    assert is_exercise(hit("exercise")) is True
    # No stored type (a library ingested before this pipeline): fall back.
    assert is_exercise(hit("")) == looks_like_exercise(text)


# -- headings and breadcrumbs ---------------------------------------------

def test_the_heading_becomes_the_section_not_an_mcq_option():
    """35% of the live library carried a useless breadcrumb.

    41 chunks were filed under the book's own running head and 88 under a
    fragment -- "(घ) झारखंड", "का नाम बता सकते हैं?", "व्यक्त करती है-". The
    breadcrumb exists to carry the chapter's vocabulary into the vector; those
    carry nothing.
    """
    tail = (
        "Exercises:",
        "1. In which of these states is black soil mainly found?",
        "(a) Punjab   (b) Haryana   (c) Maharashtra   (d) Jharkhand",
    )
    chunks, _ = ingestion.build_chunks(_two_column_pdf(LEFT, RIGHT, tail=tail), {})

    sections = {c.section for c in chunks}
    assert "Black Soil" in sections
    assert not any(s.startswith("(") for s in sections), sections


def test_a_heading_is_never_a_chunk_of_its_own():
    chunks, _ = ingestion.build_chunks(_two_column_pdf(LEFT, RIGHT), {})
    assert all(c.text.strip() != "Black Soil" for c in chunks)


# -- sizing ----------------------------------------------------------------

def test_chunks_fit_the_prompt_cap_whole():
    """The finding that drove the port: delivery, not retrieval.

    A chunk larger than `rag_passage_token_cap` is trimmed to its leading
    sentences, so the model sees the opening of it and nothing else. On the
    live library the median chunk was 344 tokens against a 70-token cap --
    16% delivery -- and the passage that answered a question routinely
    arrived without the sentence that answered it.
    """
    chunks, report = ingestion.build_chunks(_two_column_pdf(LEFT * 4, RIGHT * 4), {})
    cap = settings.rag_passage_token_cap
    assert chunks

    oversize = [c for c in chunks if c.token_estimate > cap]
    # Only a single sentence longer than the cap on its own may exceed it;
    # `trim_passage` will not cut mid-sentence.
    assert len(oversize) <= 1, [c.token_estimate for c in oversize]
    assert report["chunk"]["tokens"]["median"] <= cap


def test_trimming_is_a_no_op_on_a_chunk_from_this_pipeline():
    """The end-to-end property the whole change exists to produce."""
    chunks, _ = ingestion.build_chunks(_two_column_pdf(LEFT, RIGHT), {})
    cap = settings.rag_passage_token_cap

    for chunk in chunks:
        if chunk.token_estimate > cap:
            continue  # the oversize-sentence case, covered above
        assert trim_passage(chunk.text, "any question", cap) == chunk.text


def test_chunk_sizing_uses_the_same_estimator_as_the_prompt_budget():
    """Two estimators would put the target and the cap on different scales.

    Upstream counted Devanagari at 2.2 characters per token against this
    project's 1.2, so a chunk built to "260 tokens" measured 477 by the time
    the prompt budget looked at it.
    """
    from app.services.rag.ingestion import scripts

    assert scripts.estimate_tokens is estimate_tokens


# -- validation ------------------------------------------------------------

def test_a_shattered_text_layer_is_refused():
    """A PDF whose font has no character map still yields "text".

    It is just the wrong characters, shattered into singletons, which passes a
    letter-count check comfortably and then sits in the index as unsearchable
    noise. The old pipeline stored such a book with a warning.
    """
    doc = pymupdf.open()
    page = _page(doc)
    y = 90
    for _ in range(18):
        page.insert_text((60, y), " ".join("t h e s e a r e n o t w o r d s a t a l l"), fontsize=11)
        y += 18
    data = doc.tobytes()
    doc.close()

    _, report = ingestion.build_chunks(data, {})
    verdict = report["validate"]["verdict"]
    assert verdict["usable"] is False
    assert verdict["reason"] == "unreadable_text_layer"


def test_a_healthy_document_is_usable():
    _, report = ingestion.build_chunks(_two_column_pdf(LEFT, RIGHT), {})
    assert report["validate"]["verdict"]["usable"] is True
    assert report["validate"]["verdict"]["reason"] == "ok"


def test_an_empty_pdf_is_refused_rather_than_stored_empty():
    doc = pymupdf.open()
    _page(doc)
    data = doc.tobytes()
    doc.close()

    _, report = ingestion.build_chunks(data, {})
    assert report["validate"]["verdict"]["usable"] is False
    assert report["validate"]["verdict"]["reason"] == "no_text"


def test_a_broken_file_raises_rather_than_returning_nothing():
    with pytest.raises(ingestion.PdfExtractionError):
        ingestion.build_chunks(b"this is not a pdf", {})


# -- page furniture --------------------------------------------------------

def _book_pdf(pages=10, *, running_head="Contemporary India-2", folio=True,
              watermark=True):
    """A multi-page book with a running head, a folio and a watermark.

    The running head carries the page number with it, so the exact string
    differs on every page and exact-match counting never sees a repeat --
    which is why detection works on a number-stripped stem.
    """
    doc = pymupdf.open()
    for n in range(1, pages + 1):
        page = _page(doc)
        if running_head:
            page.insert_text((60, 45), "%s   %d" % (running_head, n), fontsize=9)
        page.insert_text((60, 90), "Chapter %d Soil" % n, fontsize=16, fontname="hebo")
        y = 130
        for line in (
            "Soil number %d is the topmost layer of the earth here." % n,
            "It supports plant life and holds water in region %d." % n,
            "Black soil number %d is found in Maharashtra." % n,
        ):
            page.insert_text((60, y), line, fontsize=11)
            y += 18
        if folio:
            page.insert_text((290, 800), str(n), fontsize=9)
        if watermark:
            page.insert_text((60, 815), "Reprint 2025-26", fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data


def test_running_head_folio_and_watermark_are_removed():
    _, report = ingestion.analyze(_book_pdf(), {})
    by_reason = report["furniture"]["blocks"]

    assert by_reason.get("running_head") == 10
    assert by_reason.get("page_number") == 10
    assert by_reason.get("watermark") == 10


def test_the_book_title_does_not_become_the_breadcrumb():
    """The 11%-of-the-library defect.

    A running head is short, set larger than the body and has no terminal
    punctuation -- the classifier's exact signature for a heading. So the
    book's own title became a section and was stamped on every passage
    beneath it, where the chapter's vocabulary should have been.
    """
    chunks, _ = ingestion.build_chunks(_book_pdf(), {})
    sections = {c.section for c in chunks}

    assert sections, "no chunks survived"
    assert "Contemporary India-2" not in sections
    assert all(s.startswith("Chapter") for s in sections), sections


def test_furniture_never_reaches_a_chunk():
    chunks, _ = ingestion.build_chunks(_book_pdf(), {})
    body = " ".join(c.text for c in chunks)

    assert "Contemporary India-2" not in body
    assert "Reprint 2025-26" not in body


def _two_column_book_with_exercise(pages=8):
    """Two columns, an exercise below them, a running head and a folio.

    The combination matters: each of the two bugs below needed all of it to
    show up, and neither appeared on a page missing any one part.
    """
    doc = pymupdf.open()
    for n in range(1, pages + 1):
        page = _page(doc)
        page.insert_text((60, 45), "Contemporary India-2   %d" % n, fontsize=9)
        page.insert_text((60, 90), "Chapter %d Black Soil" % n, fontsize=16, fontname="hebo")
        y = 130
        left = ["These soils are black in colour", "and are called regur soils here.",
                "Cotton grows well in them."]
        right = ["They occur in Maharashtra and", "Saurashtra and Malwa region %d." % n,
                 "Lava rocks formed them."]
        for a, b in zip(left, right):
            page.insert_text((60, y), a, fontsize=11)
            page.insert_text((310, y), b, fontsize=11)
            y += 18
        page.insert_text((60, 300), "Exercises", fontsize=14, fontname="hebo")
        page.insert_text((60, 325), "1. Where is black soil found in India?", fontsize=11)
        page.insert_text((60, 345), "(a) Punjab   (b) Haryana   (c) Maharashtra   (d) Jharkhand",
                         fontsize=11)
        page.insert_text((290, 800), str(n), fontsize=9)   # folio, RIGHT of the gutter
    data = doc.tobytes()
    doc.close()
    return data


def test_a_folio_does_not_drag_the_exercise_into_the_columns():
    """A stray block far below the body must not widen the two-column zone.

    The folio is printed at x=290 -- right of the gutter -- and 600 points
    below the columns. Taking the zone as one interval per column put
    everything between the body and the folio "inside" it, so the exercise
    heading was read as more of column 0 and emitted BEFORE the right-hand
    column. `add_exercise` then swallowed the column into the question: the
    lesson's own paragraphs were indexed as an exercise.
    """
    chunks, report = ingestion.build_chunks(_two_column_book_with_exercise(), {})

    prose = " ".join(c.text for c in chunks if c.content_type != "exercise")
    exercises = " ".join(c.text for c in chunks if c.content_type == "exercise")

    assert "Lava rocks formed them." in prose
    assert "Lava rocks formed them." not in exercises
    assert report["chunk"]["by_type"].get("paragraph", 0) >= 8


def test_an_exercise_run_steps_over_furniture_instead_of_absorbing_it():
    """`add_exercise` absorbs blocks up to the next heading -- but not these.

    The running head and folio printed between two pages of an exercise were
    pulled into the question, producing a chunk reading "(a) Punjab ...
    (d) Jharkhand / 1 / Contemporary India-2  2".
    """
    chunks, _ = ingestion.build_chunks(_two_column_book_with_exercise(), {})
    everything = " ".join(c.text for c in chunks)

    assert "Contemporary India-2" not in everything
    for chunk in chunks:
        assert not chunk.text.strip().endswith("1")


def test_a_short_document_keeps_everything():
    """Below six pages the statistics mean nothing.

    In a three-page handout every line looks repeated, and a threshold that
    fires there deletes real content.
    """
    _, report = ingestion.analyze(_book_pdf(pages=3), {})
    assert report["furniture"]["blocks"].get("running_head", 0) == 0


def test_a_repeated_sentence_is_not_mistaken_for_a_running_head():
    """Body prose that ends a sentence is never furniture, however repeated."""
    from app.services.rag.ingestion import furniture

    assert furniture._could_be_furniture("Contemporary India-2") is True
    assert furniture._could_be_furniture("The soil is black.") is False
    assert furniture._could_be_furniture("मृदा काली है।") is False


def test_stem_ignores_letter_spacing_and_page_number():
    from app.services.rag.ingestion import furniture

    # Letter-spaced for effect, as textbook running heads often are.
    assert furniture.stem_of("MA TTER  IN O UR  S URROUNDING S 7") == \
        furniture.stem_of("MATTER IN OUR SURROUNDINGS")

    # The invariant that makes detection work: the same head on different
    # pages collapses to one stem, even though no two pages carry the same
    # string. Note "-2" belongs to this title and is kept -- only the
    # TRAILING number goes.
    stems = {furniture.stem_of("समकालीन भारत-2  %d" % n) for n in (7, 48, 112)}
    assert len(stems) == 1
    assert stems == {"समकालीनभारत2"}


# -- stage re-entrancy -----------------------------------------------------

def test_detect_does_not_undo_normalization():
    """The bug that made the first real re-ingest unanswerable.

    `detect` is run twice on purpose: the document's language summary has to
    be recomputed once normalization has settled the text, or a Hindi textbook
    is filed as English because the only readable words in it were on the
    copyright page.

    But `detect_block` seeded `normalized_text` from the raw extraction
    unconditionally, so the second run threw stage 6 away -- the rejoined soft
    wraps, the Devanagari repairs and the inline furniture stripping all went
    back to what came out of the PDF. Every chunk in the library then ended at
    a printed LINE break rather than a sentence, which the model cannot answer
    from.
    """
    from app.services.rag.ingestion import detect
    from app.services.rag.ingestion.model import Block

    block = Block(index=0, kind="text", bbox=(0, 0, 1, 1),
                  text="raw line one\nraw line two")
    detect.detect_block(block)
    assert block.normalized_text == "raw line one\nraw line two"

    # Stage 6 rewrites it...
    block.normalized_text = "raw line one raw line two"
    # ...and a second detection pass must leave that alone.
    detect.detect_block(block)
    assert block.normalized_text == "raw line one raw line two"


def test_summarize_recounts_language_without_touching_blocks():
    from app.services.rag.ingestion import detect

    document, _ = ingestion.analyze(_prose_column_pdf(), {})
    before = [b.normalized_text for p in document.pages for b in p.text_blocks]

    summary = detect.summarize(document)
    after = [b.normalized_text for p in document.pages for b in p.text_blocks]

    assert before == after
    assert "dominant_language" in summary


def test_the_pipeline_is_the_one_that_regressed():
    """End to end: analyze() must leave prose rejoined, not raw lines.

    A newline is allowed only where a sentence ended -- `join_soft_wraps`
    keeps those deliberately, and `split_sentences` treats them as boundaries.
    A newline anywhere else is a soft wrap that was not rejoined, and it
    becomes a chunk boundary in the middle of a sentence.
    """
    document, _ = ingestion.analyze(_prose_column_pdf(), {})
    bodies = [b.normalized_text for p in document.pages for b in p.text_blocks
              if "Red soil" in b.normalized_text]

    assert bodies
    for line in bodies[0].split("\n")[:-1]:
        assert line.rstrip().endswith((".", "!", "?", "।", "॥", ":")), (
            "soft wrap not rejoined, breaks a sentence: %r" % line[-40:]
        )


# -- layout internals ------------------------------------------------------

def test_projection_measures_lines_not_blocks():
    """The reason upstream's gutter detection found nothing on this corpus.

    PyMuPDF groups a left-column line and the right-column line beside it into
    one block whose box spans the gutter. Projected at block level the page
    reads as fully covered; at line level the gap is plain.
    """
    from app.services.rag.ingestion import extract

    # Straight from extraction: `analyze` would already have split the blocks
    # at the gutter, which is the very thing this projection makes possible.
    document = extract.extract_document(_two_column_pdf(LEFT, RIGHT), {})
    page = document.pages[0]
    blocks = [b for b in page.text_blocks if b.text.strip()]

    boxes = layout._boxes(blocks)
    assert len(boxes) > len(blocks), "a line-level projection needs line boxes"

    # And the block boxes really do span the gutter, which is why projecting
    # them finds nothing.
    gutter = layout.find_gutter(page)
    assert gutter is not None
    assert any(b.bbox[0] < gutter < b.bbox[2] for b in blocks)


# -- two regressions found on page 25-26 of the real Class 10 Geography PDF ---
#
# Both put a sentence under the WRONG section heading, which is worse than a
# sentence with no heading: the index then embeds it with the wrong topic in
# front of it, and the answer to "where is black soil found?" ranked 9th.

def _wide_line(words, target_pt, fontsize=11):
    """Text just long enough to reach `target_pt` wide, so column extents are exact."""
    text = ""
    for word in words:
        if pymupdf.get_text_length(text + " " + word, fontsize=fontsize) > target_pt:
            break
        text = (text + " " + word).strip()
    return text


def test_a_picture_that_crosses_the_gutter_does_not_split_the_columns_into_bands():
    """Page 25: two figure frames straddled the gutter and each opened a band.

    The page was read left-top, right-top, [image], left-bottom, right-bottom,
    so the right column's opening sentence landed BEFORE the left column's
    heading. Only TEXT that spans the gutter (a title) cuts a page in two.
    """
    doc = pymupdf.open()
    page = _page(doc)
    words = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu".split()
    for i in range(4):  # above the picture
        page.insert_text((LEFT_X, 100 + i * 16), "LT%d " % i + _wide_line(words, 200), fontsize=11)
        page.insert_text((RIGHT_X, 100 + i * 16), "RT%d " % i + _wide_line(words, 200), fontsize=11)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pix.clear_with(200)
    page.insert_image(pymupdf.Rect(150, 180, 450, 260), pixmap=pix)  # crosses x=297
    for i in range(4):  # below the picture
        page.insert_text((LEFT_X, 290 + i * 16), "LB%d " % i + _wide_line(words, 200), fontsize=11)
        page.insert_text((RIGHT_X, 290 + i * 16), "RB%d " % i + _wide_line(words, 200), fontsize=11)

    document, _ = ingestion.analyze(doc.tobytes(), {})
    text = " ".join(b.text for b in document.pages[0].blocks if b.kind == "text")
    assert document.pages[0].column_count == 2
    # The whole left column is read before any of the right.
    assert text.index("LB3") < text.index("RT0"), text


def _two_column_page_with_gap(right_x):
    """Left column 60..~280, right column starting at `right_x`; a heading gives
    the page the second text block the gutter search requires."""
    doc = pymupdf.open()
    page = _page(doc)
    words = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi".split()
    page.insert_text((60, 70), "Heading", fontsize=18, fontname="hebo")
    for i in range(14):
        page.insert_text((60, 100 + i * 16), "L%d " % i + _wide_line(words, 210), fontsize=11)
        page.insert_text((right_x, 100 + i * 16), "R%d " % i + _wide_line(words, 520 - right_x), fontsize=11)
    return doc.tobytes()


def test_a_narrow_gutter_is_still_a_gutter():
    """Page 26: an 18pt gutter measured 3.0% of the text width against a 3.5% floor.

    The page was read as ONE column, so its right-hand heading was interleaved
    with the left column's blocks. A 14.5pt gap here (about 3.0% measured) is
    missed at 0.035 and found at 0.025.
    """
    _, report = ingestion.analyze(_two_column_page_with_gap(294), {})
    assert report["layout"]["two_column"] == 1


def test_a_gap_no_wider_than_word_spacing_is_not_a_gutter():
    """The floor is lower now; it must still not invent columns out of a wide space."""
    _, report = ingestion.analyze(_two_column_page_with_gap(290), {})  # ~10pt gap
    assert report["layout"]["two_column"] == 0
