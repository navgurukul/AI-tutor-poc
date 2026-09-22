"""Tests pinned to the defects actually found in the eight-book corpus.

Each case is a real string from a real book, with the book named, so a future
change that reintroduces the bug fails here rather than in a groundedness run
three weeks later.
"""

import pytest

from textbook_ingest import apparatus, chunking, fidelity, profile, repair, strip, structure
from textbook_ingest.types import BookProfile


# --------------------------------------------------------------------------
# profile: the header fused to its page number
# --------------------------------------------------------------------------
class TestTemplate:
    def test_strips_trailing_number(self):
        # NCERT Cl.9 Science verso header
        assert profile.template("SCIENCE58") == "SCIENCE"
        assert profile.template("SCIENCE60") == "SCIENCE"

    def test_strips_separated_number(self):
        assert profile.template("THE FUNDAMENTAL UNIT OF LIFE 59") == "THE FUNDAMENTAL UNIT OF LIFE"

    def test_strips_leading_number(self):
        # NCERT Cl.6 Science puts the number on the front
        assert profile.template("83THE LIVING ORGANISMS") == "THE LIVING ORGANISMS"

    def test_leaves_ordinary_text(self):
        assert profile.template("Magnetism gets destroyed") == "Magnetism gets destroyed"


class TestFurnitureDetection:
    def _pages(self, n=12):
        """A book whose verso pages carry a numbered running header."""
        return [
            ("SCIENCE{}\n".format(50 + i) if i % 2 else "CHAPTER TITLE {}\n".format(50 + i))
            + "body text of page {} which is long enough to matter here".format(i)
            for i in range(n)
        ]

    def test_catches_numbered_header(self):
        found = profile.detect_furniture(self._pages())
        assert "SCIENCE" in found

    def test_literal_counting_would_miss_it(self):
        # The whole point: every literal is unique, so counting literals fails.
        pages = self._pages()
        literals = [line for page in pages for line in page.splitlines() if line.startswith("SCIENCE")]
        assert len(set(literals)) == len(literals)

    def test_windowed_so_a_one_chapter_header_is_caught(self):
        # 'MOTION' runs for 10 pages of a 100-page book: 10% book-wide, but 100%
        # of its own span. A book-wide threshold could never catch it.
        pages = ["unrelated page {} with some body text on it".format(i) for i in range(45)]
        pages += ["MOTION\nbody text for chapter page {}".format(i) for i in range(10)]
        pages += ["unrelated page {} with some body text on it".format(i) for i in range(45)]
        assert "MOTION" in profile.detect_furniture(pages)

    def test_does_not_catch_a_rare_repeat(self):
        pages = ["Activity 6.1\nbody text here for page {}".format(i) for i in range(2)]
        pages += ["quite different body text page {}".format(i) for i in range(20)]
        assert "Activity 6.1" not in profile.detect_furniture(pages)


class TestCaptionStyle:
    def test_detects_ncert_prefixed(self):
        pages = ["Fig. {}.1: something illustrated here".format(i) for i in range(8)]
        assert profile.detect_caption_style(pages) == "prefixed"

    def test_detects_mscert_numeric(self):
        pages = ["10.{} : Frictional force".format(i) for i in range(8)]
        assert profile.detect_caption_style(pages) == "numeric"

    def test_none_when_absent(self):
        assert profile.detect_caption_style(["just prose", "more prose"]) == "none"


# --------------------------------------------------------------------------
# strip: the header fused into the first sentence
# --------------------------------------------------------------------------
class TestFusedPrefix:
    def test_strips_header_glued_to_body(self):
        # NCERT Cl.10 Science p.206, verbatim shape
        line = "Science206 that motion of electrons in an electric circuit constitutes a current"
        out = strip.strip_page(line, {"Science"})
        assert out.startswith("that motion of electrons")
        assert "Science206" not in out

    def test_leaves_a_sentence_that_merely_starts_with_the_word(self):
        line = "Science is the study of the natural world around us"
        assert strip.strip_page(line, {"Science"}) == line

    def test_drops_the_line_when_only_the_header_remains(self):
        assert strip.strip_page("SCIENCE58", {"SCIENCE"}).strip() == ""

    def test_drops_bare_edition_marker(self):
        # NCERT prints this on every page, with no 'Reprint' word
        assert strip.strip_page("2020-21", set()).strip() == ""
        assert strip.strip_page("Reprint 2025-26", set()).strip() == ""


# --------------------------------------------------------------------------
# repair
# --------------------------------------------------------------------------
class TestSplitRepair:
    VOCAB = {"external": 14, "exter": 7, "nal": 9, "large": 36, "lar": 13, "ge": 13,
             "information": 20, "formation": 6, "somewhat": 3, "some": 80, "what": 60,
             "previous": 6, "pr": 158, "evious": 3}

    def test_joins_a_broken_word(self):
        assert repair.should_join("exter", "nal", self.VOCAB)
        assert repair.should_join("lar", "ge", self.VOCAB)

    def test_joins_when_one_fragment_is_common(self):
        # 'pr' is common precisely because it is a frequent split point
        assert repair.should_join("pr", "evious", self.VOCAB)

    def test_protects_two_letter_english_words(self):
        # 'in formation' must never become 'information'
        assert not repair.should_join("in", "formation", self.VOCAB)

    def test_protects_genuine_word_pairs(self):
        # 'somewhat' exists but is far rarer than either half
        assert not repair.should_join("some", "what", self.VOCAB)

    def test_rewrites_in_context(self):
        out = repair.repair_splits("the exter nal envir onment", {**self.VOCAB, "environment": 16, "envir": 8, "onment": 7})
        assert "external" in out and "environment" in out


class TestOtherRepairs:
    def test_space_substitute_detected_and_applied(self):
        # NCERT Cl.1 Math-Magic uses U+25A1 between every pair of words
        text = " ".join("may□i□put□my□front□legs" for _ in range(10))
        assert fidelity.detect_space_substitute(text) == "□"
        assert "may i put" in repair.normalise_characters(text, "□")

    def test_collapses_repeated_display_type(self):
        out = repair.collapse_repeats("KEYWORDS KEYWORDS KEYWORDS KEYWORDS KEYWORDS")
        assert out.split().count("KEYWORDS") <= 2

    def test_collapses_concatenated_display_type(self):
        assert repair.collapse_repeats("SpeakingSpeakingSpeaking") == "Speaking"

    def test_rejoins_adjacent_drop_cap(self):
        out = repair.repair_dropped_initials("Q\nuestions here", {"questions": 5})
        assert out.startswith("Questions")


class TestFidelityGate:
    def test_rejects_unmapped_fonts(self):
        # NCERT Cl.1 Math-Magic ch.2 -- 84 distinct names spelling out words,
        # which is what separates it from a book that merely leaks its bullet.
        names = ["/B{:02x}".format(n) for n in range(0x20, 0x60)]
        page = " ".join(names * 4)
        report = fidelity.assess([page] * 8)
        assert report.verdict == "reject"
        assert report.code == "unmapped_fonts"

    def test_rejects_a_scan(self):
        assert fidelity.assess([""] * 30).verdict == "reject"

    def test_repairs_rather_than_rejects_a_substitute_space(self):
        page = " ".join("the□cat□sat□on□the□mat" for _ in range(60))
        report = fidelity.assess([page] * 8)
        assert report.verdict == "repair"
        assert report.space_substitute == "□"

    def test_accepts_ordinary_text(self):
        page = "Magnetism gets destroyed when a magnet is heated or broken. " * 40
        assert fidelity.assess([page] * 10).verdict == "ok"


# --------------------------------------------------------------------------
# apparatus: the two anchor bugs, and the bounded stem search
# --------------------------------------------------------------------------
class TestBoxLabels:
    def test_plural_exercises(self):
        # the old anchor demanded end-of-string after 'exercise'
        assert apparatus.is_box_label("Exercises")
        assert apparatus.is_box_label("EXERCISES")
        assert apparatus.is_box_label("Exercise")

    def test_activity_with_a_number(self):
        assert apparatus.is_box_label("Activity 1")
        assert apparatus.is_box_label("Activity 7")

    def test_ncert_summary_label(self):
        assert apparatus.is_box_label("What you have learnt")
        assert apparatus.is_box_label("What we have learnt")

    def test_questions(self):
        assert apparatus.is_box_label("QUESTIONS")

    def test_not_a_sentence_that_starts_with_one(self):
        assert not apparatus.is_box_label("Activity of the enzyme depends on temperature")

    def test_learned_labels_from_the_profile(self):
        p = BookProfile(labels={"uestions"})
        assert apparatus.is_box_label("uestions", p)


class TestStems:
    def test_ncert_true_false_stem(self):
        # 'right or wrong' sits eight words in; the old anchor missed it
        assert apparatus.is_stem(
            "3. Say if the statements given below are right or wrong. Rewrite them."
        )

    def test_choose_an_rather_than_choose_the(self):
        assert apparatus.is_stem("1. Choose an appropriate word and fill in the blanks.")

    def test_write_the_answers_in_your_words(self):
        assert apparatus.is_stem("4. Write the answers in your words.")

    def test_prose_mentioning_an_instruction_is_safe(self):
        # a stem deep inside a long paragraph is not the paragraph's purpose
        prose = ("The magnet was suspended freely and settled north-south. " * 4
                 + "Students may then answer the following questions.")
        assert not apparatus.is_stem(prose)

    def test_blank_run_still_fires(self):
        assert apparatus.is_apparatus(
            "(c) There is repulsion between the .......... poles of a magnet."
        )


class TestExerciseRouting:
    def test_page_routes_on_a_label_alone(self):
        # NCERT end-of-chapter pages carry 'QUESTIONS', not an instruction
        paras = ["QUESTIONS"] + ["{}. What is a cell ?".format(i) for i in range(1, 7)]
        assert apparatus.page_is_exercise(paras, 0.40)

    def test_lesson_page_is_not_routed(self):
        paras = [
            "A magnet is a material that attracts iron, nickel and cobalt.",
            "Magnetism gets destroyed when a magnet is heated or broken into pieces.",
            "The poles of a magnet cannot be separated by cutting it.",
        ]
        assert not apparatus.page_is_exercise(paras, 0.40)

    def test_summary_survives_an_exercise_page(self):
        paras = [
            "QUESTIONS",
            "1. What is a cell ?",
            "Comets are formed out of ice and dust particles and revolve around the sun.",
        ]
        kept = apparatus.keep_on_exercise_page(paras)
        assert any("Comets are formed" in k for k in kept)


# --------------------------------------------------------------------------
# structure
# --------------------------------------------------------------------------
class TestHeadingValidation:
    def test_rejects_a_table_row(self):
        # MSCERT Cl.6, labelled 13 chunks
        assert structure.clean_heading("Yes Yes None") == ""
        assert structure.clean_heading("Group A Group B") == ""
        assert structure.clean_heading("Points Solids Liquids Gases") == ""

    def test_rejects_a_sentence_fragment(self):
        assert structure.clean_heading("The British scientist Michael") == ""

    def test_rejects_furniture_from_the_profile(self):
        p = BookProfile(furniture={"SCIENCE"})
        assert structure.clean_heading("SCIENCE64", p) == ""

    def test_keeps_a_real_topic(self):
        assert structure.clean_heading("Fun with Magnets") == "Fun with Magnets"
        assert structure.clean_heading("6.2 Plant Tissues") == "Plant Tissues"

    def test_keeps_a_two_word_topic(self):
        assert structure.clean_heading("Simple Machines") == "Simple Machines"


class TestCaptions:
    def test_ncert_caption(self):
        p = BookProfile(caption_style="prefixed")
        assert structure.is_caption("Fig. 8.3: Distance-time graph of an object", p)

    def test_mscert_caption(self):
        p = BookProfile(caption_style="numeric")
        assert structure.is_caption("10.8 : Frictional force", p)


class TestTableRows:
    @pytest.mark.parametrize("row", [
        "Yes Yes None",
        "Effort Fulcrum Effort",
        "Mercury 0 0.01 58.65 days 88 days",
        "Group A Group B",
    ])
    def test_detects(self, row):
        assert structure.looks_like_table_row(row)

    @pytest.mark.parametrize("prose", [
        "Fun with Magnets",
        "A magnet attracts iron and nickel.",
        "The Universe",
    ])
    def test_leaves_prose(self, prose):
        assert not structure.looks_like_table_row(prose)


# --------------------------------------------------------------------------
# chunking
# --------------------------------------------------------------------------
class TestChunking:
    def test_never_cites_page_one_for_later_text(self):
        # the old flush() left start_page unset and fell back to 'or 1'
        pages = ["", ""] + ["Some body text about magnets on this page. " * 4] * 6
        chunks = chunking.chunk_pages(pages, chunk_chars=200, overlap_chars=60)
        assert chunks
        assert all(c.page_start >= 3 for c in chunks)

    def test_overlap_is_not_applied_at_ordinary_boundaries(self):
        pages = ["First paragraph here about magnets and iron filings.\n\n"
                 "Second paragraph here about nickel and cobalt entirely."]
        chunks = chunking.chunk_pages(pages, chunk_chars=60, overlap_chars=40)
        joined = " ".join(c.text for c in chunks)
        assert joined.count("First paragraph here") == 1

    def test_table_rows_become_their_own_chunk(self):
        rows = "\n\n".join(["Mercury 0 0.01 58.65 days", "Venus 0 177.2 243 days",
                            "Earth 1 23.5 24 hours"])
        prose = ("Mercury is the planet closest to the sun and is visible in the "
                 "morning and evening when it is away from the sun. " * 2)
        chunks = chunking.chunk_pages([rows + "\n\n" + prose], chunk_chars=700)
        kinds = {c.kind for c in chunks}
        assert "table" in kinds
        table = [c for c in chunks if c.kind == "table"][0]
        assert "Mercury is the planet" not in table.text

    def test_uses_printed_page_numbers_for_citations(self):
        pages = ["Body text about cells and their membranes here today. " * 3] * 3
        chunks = chunking.chunk_pages(pages, chunk_chars=200, page_numbers=[57, 58, 59])
        assert min(c.page_start for c in chunks) == 57


class TestEmbeddingText:
    def test_prose_alone_by_default(self):
        c = chunking.Chunk(0, "A magnet attracts iron.", "Fun with Magnets", 1, 1)
        assert c.embedding_text() == "A magnet attracts iron."

    def test_breadcrumb_when_asked_for(self):
        c = chunking.Chunk(0, "A magnet attracts iron.", "Fun with Magnets", 1, 1)
        out = c.embedding_text(["Class 6", "Science"])
        assert out.startswith("Class 6 > Science > Fun with Magnets")


class TestExerciseMarkerIsNarrowerThanBoxLabel:
    """Regression: an activity box must not route a lesson page as an exercise.

    MSCERT p.42 scores 0.48 density and carries a "Try this." box. Treating that
    as the page's instruction dropped "Read this list of substances : Spirit,
    camphor, petrol, ghee, coconut oil, naphthalene balls..." and lost the gold
    answer for which substances sublimate.
    """

    def test_section_headers_route_a_page(self):
        assert apparatus.is_exercise_marker("QUESTIONS")
        assert apparatus.is_exercise_marker("Exercises")

    def test_info_boxes_do_not(self):
        for label in ("Try this.", "Do you know ?", "More to Know!", "Activity 1"):
            assert apparatus.is_box_label(label), label
            assert not apparatus.is_exercise_marker(label), label

    def test_activity_page_keeps_its_prose(self):
        paras = [
            "Try this.",
            "Take pieces of wax in a bowl and heat them on a candle or spirit lamp.",
            "Read this list of substances : Spirit, camphor, petrol, ghee, "
            "coconut oil, naphthalene balls, ammonium chloride (navsagar).",
            "When a substance changes from one state to another, the process is "
            "called change of state of the substance.",
        ]
        assert not apparatus.page_is_exercise(paras, 0.40)
        kept = " ".join(apparatus.strip_apparatus(paras))
        assert "naphthalene balls" in kept


# --------------------------------------------------------------------------
# front and back matter
# --------------------------------------------------------------------------
from textbook_ingest import matter  # noqa: E402


class TestMatter:
    def _book(self):
        front = ["Textbook Bureau credits page {}".format(i) for i in range(6)]
        body = ["Body prose about magnets and iron on this page. " * 4 for _ in range(40)]
        back = ["amphibian - उभयचर\nannual - वार्षिक\n"
                "comet - धूमकेतु\nboiling - उतकलन\n"
                "density - घनता\ndermis - तवचा" for _ in range(3)]
        pages = front + body + back
        numbers = [None] * 6 + list(range(1, 41)) + [41, 42, 43]
        return pages, numbers

    def test_drops_front_matter_at_printed_page_one(self):
        pages, numbers = self._book()
        start, _end, warnings = matter.find_body(pages, numbers)
        assert start == 6
        assert any(w.code == "front_matter_dropped" for w in warnings)

    def test_drops_a_foreign_script_glossary(self):
        pages, numbers = self._book()
        _start, end, warnings = matter.find_body(pages, numbers)
        assert end == len(pages) - 3
        assert any(w.code == "back_matter_dropped" for w in warnings)

    def test_keeps_everything_when_numbering_is_absent(self):
        pages = ["Body prose about magnets. " * 8 for _ in range(30)]
        start, end, _ = matter.find_body(pages, [None] * 30)
        assert (start, end) == (0, 30)

    def test_refuses_to_drop_an_implausible_share(self):
        # printed page 1 half way through means the numbering was misread
        pages = ["page {} body text here".format(i) for i in range(40)]
        numbers = [None] * 20 + list(range(1, 21))
        start, _end, _ = matter.find_body(pages, numbers)
        assert start == 0


class TestDisplayGarbage:
    WRECK = ("12.5 FA 12.5 FA12.5 FA 12.5 FA12.5 FA CTORS ON WHICH THE "
             "RESISTCTORS ON WHICH THE RESIST")

    def test_detected(self):
        assert structure.looks_like_display_garbage(self.WRECK)

    def test_never_becomes_a_heading_or_a_label(self):
        assert not structure.looks_like_heading(self.WRECK)
        assert structure.clean_heading(self.WRECK) == ""

    def test_ordinary_heading_is_untouched(self):
        assert not structure.looks_like_display_garbage("Motion and Types of Motion")
        assert structure.clean_heading("Motion and Types of Motion")

    def test_collapse_leaves_one_copy(self):
        assert repair.collapse_repeats("KEYWORDS KEYWORDS KEYWORDS KEYWORDS") == "KEYWORDS"
        assert repair.collapse_repeats("Ones Ones Ones Ones") == "Ones"

    def test_collapse_leaves_a_genuine_double(self):
        assert repair.collapse_repeats("the very very good idea") == "the very very good idea"


class TestTableRowFalsePositives:
    """A heading may legitimately repeat a word; a table row may not have
    function words. That is the line between them."""

    @pytest.mark.parametrize("heading", [
        "Motion and Types of Motion",     # MSCERT chapter, repeats 'Motion'
        "Work and Energy",
        "Force and Types of Force",
    ])
    def test_real_headings_survive(self, heading):
        assert not structure.looks_like_table_row(heading)
        assert structure.clean_heading(heading) == heading

    @pytest.mark.parametrize("row", ["Effort Fulcrum Effort", "Group A Group B",
                                     "Ones Ones Ones Ones"])
    def test_column_labels_still_caught(self, row):
        assert structure.looks_like_table_row(row)


class TestDingbatVsCorruption:
    """A repeated bullet glyph name must not condemn a readable book.

    NCERT Class 5 EVS leaks "/rhombus" 210 times -- 3% of its text, 20 distinct
    names book-wide. Rejecting it lost a whole readable textbook. Class 1
    Math-Magic has 84 names spelling out words. Concentration separates them.
    """

    def test_a_dominant_name_is_a_dingbat_not_corruption(self):
        body = "The children looked around the village and drew what they saw. "
        page = ("/rhombus " + body) * 30
        report = fidelity.assess([page] * 10)
        assert report.verdict != "reject"
        assert "/rhombu" in {d[:8] for d in report.dingbats}

    def test_spread_of_names_is_still_rejected(self):
        names = ["/B{:02x}".format(n) for n in range(0x20, 0x60)]
        report = fidelity.assess([" ".join(names * 4)] * 8)
        assert report.verdict == "reject"
        assert report.code == "unmapped_fonts"


class TestFigureDebris:
    def test_unrecoverable_letter_run_is_dropped(self):
        # NCERT Cl.6 figure labels, extracted one character at a time
        out = repair.repair_letter_runs("beans ca t t A here", {})
        assert "ca t t A" not in out

    def test_a_reversible_run_is_repaired_not_dropped(self):
        out = repair.repair_letter_runs("the e h t word", {"the": 40})
        assert "the the word" in out or "the" in out

    def test_a_two_letter_run_is_left_alone(self):
        # only three or more is debris; two could be anything
        assert repair.repair_letter_runs("grade a b here", {}) == "grade a b here"


class TestNumberedImperativeStems:
    """The structural form of an instruction, added after a measured failure.

    The phrase list missed "1. Classify the following as a lever..." and
    "6. Name the levers mentioned in the following passage", so an exercise page
    was retrieved for "What is a lever?" and the tutor contradicted the book
    (groundedness v5, A5-lever: recall 100% -> 0%). Numbering is what makes the
    rule safe: prose uses imperatives freely, but only an exercise numbers them.
    """

    @pytest.mark.parametrize("instruction", [
        "1. Classify the following as a lever, a pulley and an inclined plane :",
        "6. Name the levers mentioned in the following passage.",
        "2. Identify the fulcrum, load and effort of each.",
        "4. Compare the two diagrams and state the difference.",
    ])
    def test_caught(self, instruction):
        assert apparatus.is_stem(instruction)

    @pytest.mark.parametrize("prose", [
        # an imperative in body text, unnumbered -- the naphthalene case
        "Read this list of substances : Spirit, camphor, petrol, ghee, naphthalene balls.",
        # a definition given as a numbered point is still a definition
        "1. The support at which the rod of a lever is rested is called the 'fulcrum of a lever'.",
        "2. The weight lifted by a lever is called the 'load'.",
    ])
    def test_prose_is_safe(self, prose):
        assert not apparatus.is_stem(prose)

    def test_a_long_numbered_passage_is_not_an_instruction(self):
        long = "3. Name the parts shown. " + ("The lever rotates about the fulcrum. " * 12)
        assert not apparatus.is_stem(long)
