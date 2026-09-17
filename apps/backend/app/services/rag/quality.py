"""Textbook apparatus that must never reach an embedding.

A school textbook is not all prose. Around the explanations sit activity boxes,
"Try this", end-of-chapter exercises, fill-in-the-blanks, match-the-pairs and
true/false lists -- and every one of them is *about* the chapter's topic, so it
embeds close to the definition a student is asking for and competes with it.

Three things this removes, in order of how much damage they do.

1. FILL-IN-THE-BLANKS, WHERE THE PUBLISHER DELETED THE ANSWER.
   The measured case, from the groundedness run of 2026-09-16: "What are the
   poles of a magnet?" retrieved p.121 first --

       (c) There is repulsion between the .......... poles of a magnet,
           and attraction between its ............ poles.

   -- and the tutor, reading a sentence with the two words removed, filled them
   in the wrong way round and told the student that opposite poles repel. The
   passage ranks first because it is a near-verbatim copy of the definition on
   p.117 with the answer taken out, so no distance threshold can separate them.
   This is the single highest-value thing in this module.

2. TRUE/FALSE AND "RIGHT OR WRONG" LISTS, WHICH ARE DELIBERATELY FALSE.
   "(a) Bones are soft." (p.74), "(a) There are no joints in our body." (p.74),
   "(a) Land and soil are the same thing." (p.18). Stripped of the instruction
   that makes them a question, these are flat assertions of the opposite of what
   the book teaches, sitting in the index waiting to be retrieved.

3. BARE QUESTIONS AND BOX LABELS. Activity prompts with no answer, and the
   furniture itself -- "Try this.", "Use your brain power !", "Do you know ?" --
   which survive extraction as text and dilute every vector they land in.

WHY THIS FILTERS PARAGRAPHS AND NOT CHUNKS
------------------------------------------
Because on a two-column page the exercise is interleaved with the prose, line by
line, and a chunk holds both. Chunk 279 of the shipped index is the friction
definition -- "The smooth surfaces can be easily rubbed against each other
because the force of friction between them is less" -- with a fill-in-the-blanks
tail glued to it. Dropping that chunk would delete the answer to "What is
frictional force?". Dropping the tail keeps it.

So `is_apparatus` runs per paragraph, inside chunk_pages, before anything is
merged. A chunk that was *entirely* apparatus then disappears on its own,
because nothing is left to put in it.

WHAT IS DELIBERATELY KEPT
-------------------------
* "What we have learnt" summaries. The label is furniture; the bulleted lines
  under it are the chapter's own definitions, restated compactly, and they are
  some of the best retrieval material in the book.
* Rhetorical questions inside prose ("Why does this happen ?"), because the
  answer is the next sentence and cutting the question strands it.
* Anything this module is not sure about. A false positive deletes a fact a
  student needs and no later stage can put it back; a false negative leaves one
  noisy line in a chunk. The two are not equally bad, and the rules below are
  written accordingly.
"""

import re
from typing import List

# --------------------------------------------------------------------------
# 1. blanks: the publisher removed the answer
# --------------------------------------------------------------------------
# Four or more dots, or three or more underscores, in a row. The body text of
# this book never does this; a leader in the table of contents and a blank to
# be filled both do. Three dots are excluded on purpose -- that is an ellipsis,
# which shorten_passage itself inserts.
_BLANK_RUN = re.compile(r"\.{4,}|_{3,}|…{2,}")

# --------------------------------------------------------------------------
# 2. exercise instructions
# --------------------------------------------------------------------------
# The stem that turns the lines after it into exercise material. Matched at the
# START of a paragraph only, optionally behind a list number ("3. Fill in the
# blanks..."), so a sentence that merely mentions one of these phrases in prose
# is untouched.
_EXERCISE_STEM = re.compile(
    r"^(?:\(?[0-9ivx]{1,3}[.)]\s*)?"
    r"(?:"
    r"fill\s+in\s+the\s+blank|"
    r"match\s+the|"
    r"true\s+or\s+false|"
    r"true\s+of\s+false|"          # the book's own typo, p.18
    r"right\s+or\s+wrong|"
    r"odd\s+one\s+out|"
    r"who\s+is\s+the\s+odd|"
    r"choose\s+the\s+(?:correct|term|proper|appropriate)|"
    r"select\s+the\s+(?:correct|proper)|"
    r"write\s+(?:the\s+)?answers?\s+to\s+the\s+following|"
    r"answer\s+the\s+following|"
    r"answer\s+in\s+your\s+own\s+words|"
    r"write\s+in\s+your\s+own\s+words|"
    r"give\s+scientific\s+reasons|"
    r"solve\s+the\s+following|"
    r"complete\s+the\s+(?:following|statements|table)|"
    r"put\s+a\s+.{0,6}\s*mark|"
    r"spot\s+the\s+following|"
    r"draw\s+(?:labelled\s+)?diagrams?\b|"
    r"use\s+the\s+words|"
    r"words?\s+from\s+the\s+brackets|"
    r"term\s+from\s+the\s+brackets|"
    r"name\s+them\b|"
    r"what\s+will\s+happen\s+if|"
    r"why\s+is\s+it\s+said\s+that"
    r")",
    re.IGNORECASE,
)

# Box and section furniture: a whole paragraph that is only a label. Anchored at
# both ends, so a line that goes on to say something is never dropped for
# opening with one of these.
_BOX_LABEL = re.compile(
    r"^(?:"
    r"(?:let'?s\s+)?try\s+this|"
    r"do\s+you\s+know|"
    r"can\s+you\s+tell|"
    r"can\s+you\s+recall|"
    r"use\s+your\s+brain\s+power|"
    r"observe\s+and\s+discuss|"
    r"find\s+out|"
    r"always\s+remember|"
    r"science\s+watch|"
    r"what\s+we\s+have\s+learnt|"
    r"exercise|"
    r"activity|"
    r"project|"
    r"a\s+little\s+fun|"
    r"in\s+the\s+past|"
    r"think\s+about\s+it|"
    r"introduction"
    r")"
    r"[\s.:;!?…\-]*$",
    re.IGNORECASE,
)

# A row of a match-the-pairs table: "(2) Oxygen (b) Rain", "(4) Saturn (d) Sirius".
_PAIR_ROW = re.compile(r"^\(?\w{1,3}[.)]\s*\S.{0,40}?\(\w{1,3}[.)]\s*\S")

# "(a) ... (b) ... (c) ..." -- three or more lettered options in one paragraph is
# an exercise list, not prose.
_OPTION_MARKER = re.compile(r"\(\s*[a-z0-9]{1,2}\s*\)")

# A numbered exercise question, which reflow often splits before its own
# question mark: "4. What is sublimation ? Write the" ends one paragraph and
# "names of everyday substances that sublimate." begins the next. Left in, that
# first fragment became the top hit for "What is sublimation?" -- a near-perfect
# embedding match for the student's question that answers none of it, ranked
# above the definition on p.46. Short and numbered and carrying a question mark
# anywhere in it; body prose asks rhetorical questions but does not number them.
_NUMBERED_QUESTION = re.compile(r"^\(?[0-9ivx]{1,3}[.)]\s+[^.]*\?")

_LETTERS = re.compile(r"[A-Za-z]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def is_apparatus(paragraph: str) -> bool:
    """True for a paragraph that is exercise or activity furniture.

    Runs on one reflowed paragraph, which on a two-column page is often a single
    visual line -- which is exactly the granularity needed, because that is how
    finely the exercise is interleaved with the prose.
    """
    text = " ".join((paragraph or "").split())
    if not text:
        return False

    # A blank where the answer used to be. Unconditional: there is no sentence
    # worth keeping that also has a row of dots in it.
    if _BLANK_RUN.search(text):
        return True
    if _BOX_LABEL.match(text):
        return True
    if _EXERCISE_STEM.match(text):
        return True
    if _PAIR_ROW.match(text) and len(text) < 120:
        return True
    # Three or more lettered options, and little else -- an answer list.
    if len(_OPTION_MARKER.findall(text)) >= 3:
        return True
    if _NUMBERED_QUESTION.match(text) and len(text) < 100:
        return True
    return False


def strip_apparatus(paragraphs: List[str]) -> List[str]:
    """The paragraphs worth embedding, in order.

    Once an exercise stem has been seen, the lettered items belonging to it
    follow as their own paragraphs and are dropped by the option and blank rules
    above -- but a bare "(a) Bones are soft." carries no blank and only one
    marker, so it would survive on its own. So a stem also suppresses the short
    lettered items immediately after it, which is what removes the true/false
    statements that assert the opposite of what the chapter teaches.

    The suppression ends at the first paragraph that is neither a lettered item
    nor apparatus, so it cannot run away into the next section's prose.
    """
    out: List[str] = []
    in_exercise = False
    for para in paragraphs:
        text = " ".join((para or "").split())
        if not text:
            continue
        if _EXERCISE_STEM.match(text):
            in_exercise = True
            continue
        if is_apparatus(text):
            # A box label ends the run: "Try this." separates the exercise from
            # whatever the page does next.
            if _BOX_LABEL.match(text):
                in_exercise = False
            continue
        if in_exercise and (_is_exercise_item(text) or len(text) < 80):
            # Short lines keep the run alive as well as ending in it. Reflow
            # splits the instruction itself on a narrow column -- "3. Right or
            # wrong ? If wrong, write the" / "correct sentence." -- and without
            # this the run ends on that continuation and the items after it
            # ("(a) Bones are soft.") survive as flat assertions of the
            # opposite of what the chapter teaches.
            continue
        in_exercise = False
        out.append(para)
    return out


def _is_exercise_item(text: str) -> bool:
    """A lettered or numbered item belonging to the exercise stem above it.

    Two shapes, because reflow splits the stem itself mid-sentence on a narrow
    column. "3. Right or wrong ? If wrong, write the" ends one paragraph and
    "correct sentence. (a) Bones are soft. (b) The human skeleton protects the
    internal organs." begins the next -- so the items do not always start with
    their own marker, and matching only on the opening left "Bones are soft" in
    the index as a flat assertion.

    Both shapes are length-capped, and both only ever apply while an exercise
    stem is open: long prose that happens to carry list markers is untouched,
    because a definition given as a numbered point is still a definition.
    """
    if len(text) > 300:
        return False
    if re.match(r"^\(?[a-z0-9]{1,2}[.)]\s", text, re.IGNORECASE) and len(text) <= 200:
        return True
    return len(_OPTION_MARKER.findall(text)) >= 2


# --------------------------------------------------------------------------
# 3. whole exercise pages
# --------------------------------------------------------------------------
def exercise_density(paragraphs: List[str]) -> float:
    """Share of a page's paragraphs that are exercise apparatus.

    The page is judged as a whole because no single item condemns it: an
    exercise is a spread of short stems, options and blanks.

    Counted per paragraph, so the number moves with how reflow draws
    paragraphs. It used to split every visual line, which made a lesson page
    look like dozens of harmless paragraphs; now that a prose paragraph stays
    whole while each exercise item is still its own, a lesson page scores
    higher than it did. page_is_exercise's stem requirement is what keeps that
    safe -- see there.
    """
    paragraphs = [" ".join((p or "").split()) for p in paragraphs]
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        return 0.0
    bad = sum(
        1 for p in paragraphs
        if is_apparatus(p) or _EXERCISE_STEM.match(p) or _OPTION_MARKER.findall(p)
    )
    return bad / len(paragraphs)


_BULLET = re.compile(r"^[l•●·]\s+")


def keep_on_exercise_page(paragraphs: List[str]) -> List[str]:
    """The prose worth keeping from a page that is otherwise an exercise.

    Dropping such a page whole was the first version of this, and it was wrong:
    the end-of-chapter exercise shares its page with "What we have learnt", the
    chapter's own summary, and those lines are some of the densest definitions
    in the book. Measured on the Class 6 book, dropping the twelve exercise
    pages outright removed 20 declarative summary lines that appear nowhere
    else in the corpus -- including "A diet containing all nutrients in the
    right quantity is called a balanced diet" (p.66), "Nutrition is the process
    of taking food and water..." (p.66) and the whole universe summary (p.128).

    So the page is filtered hard rather than deleted. A paragraph survives only
    if it states something: no apparatus, no option markers at all (one is
    enough to condemn it here, where the surrounding page is an exercise), not
    an instruction, not a bare question, and long enough to be a clause rather
    than a fragment of a numbered item.

    The four-word floor relies on reflow keeping a wrapped sentence together.
    It did not always: "Soil has both biotic and abiotic" and "constituents."
    used to arrive as two paragraphs, and the floor would have taken the second.
    """
    out: List[str] = []
    for para in paragraphs:
        text = " ".join((para or "").split())
        if not text or is_apparatus(text) or _EXERCISE_STEM.match(text):
            continue
        if _OPTION_MARKER.search(text):
            continue
        body = _BULLET.sub("", text)
        if _IMPERATIVE.match(body):
            continue
        if body.rstrip().endswith("?"):
            continue
        if len(body.split()) < 4:
            # A section heading is short by nature, and dropping it would strip
            # the breadcrumb off everything the summary contributes. Kept only
            # when it survives clean_heading, so an exercise heading still goes.
            from app.services.rag.pdf_text import looks_like_heading

            if looks_like_heading(body) and clean_heading(body):
                out.append(body)
            continue
        out.append(body)
    return out


def page_is_exercise(paragraphs: List[str], ratio: float = 0.40) -> bool:
    """True for a page that is an exercise, not a lesson.

    Two conditions, because either alone misfires. The density catches the page;
    requiring at least one explicit instruction stem ("Fill in the blanks",
    "Match the pairs") stops a legitimate page of worked examples or a figure
    table, which is full of "(a)" markers and no instructions, from going with
    it.

    Density alone does not separate the two, and the stem is load-bearing.
    Measured over this book with reflow keeping paragraphs whole, lesson pages
    holding an answer reach 0.43 (p.42, p.36, p.86) and exercise pages start at
    0.44 -- no gap -- but none of those lesson pages carries a stem. Checked
    against all 69 answer phrases in the two evaluation sets (benchmark.py's
    ANSWER_KEY and docs/groundedness/evalset.json): at 0.40, 16 pages are
    treated as exercises, 14.8% of the text goes, and **no answer phrase is
    lost** from the corpus. Two of those pages (p.79, p.100) are fill-in-the-
    blanks the filter used to miss, because the old line-splitting broke their
    instruction in half.

    Re-measure this if the book changes. `scripts/eval/corpus_filter_report.py`
    prints the density table and the answer-phrase check.
    """
    return exercise_density(paragraphs) >= ratio and any(
        _EXERCISE_STEM.match(" ".join((p or "").split())) for p in paragraphs
    )


# --------------------------------------------------------------------------
# 4. chunks that ask without answering
# --------------------------------------------------------------------------
def is_question_only(text: str) -> bool:
    """True when nothing in this text states anything.

    An activity prompt -- "To which part of plants are butterflies and insects
    attracted ?" -- embeds beautifully against the question a student asks and
    answers none of it. Whole-chunk test, applied after paragraphs have been
    merged, so a rhetorical question inside prose is safe: its chunk has plenty
    of declarative sentences.
    """
    flat = " ".join((text or "").split())
    if not flat:
        return True
    sentences = [s for s in _SENTENCE_SPLIT.split(flat) if len(s.strip()) > 3]
    if not sentences:
        return True
    return all(s.rstrip().endswith("?") for s in sentences)


# --------------------------------------------------------------------------
# 5. the breadcrumb heading
# --------------------------------------------------------------------------
# Imperatives that start an activity step. "3. Rub a peacock feather between two
# pages of a notebook" is picked up as a heading by looks_like_heading -- it is
# short, capitalised and has no full stop -- and then labels a chunk of the
# friction section with a sentence about peacock feathers.
_IMPERATIVE = re.compile(
    r"^(?:rub|take|hold|observe|spread|collect|write|draw|go\b|put|stir|fill|"
    r"choose|match|find|make|prepare|name|give|solve|complete|identify|classify|"
    r"read|visit|cut|place|keep|bring|tie|repeat|note|discuss|think|look|try|"
    r"measure|count|list|state|explain|describe|answer|select|arrange|fix|"
    r"switch|pour|drop|press|push|pull|move|tell|ask|compile|obtain)\b",
    re.IGNORECASE,
)
# "10.8 : Frictional force" -- a figure caption. The number is noise, the words
# after it are the topic, so the number is stripped rather than the line dropped.
_FIGURE_NUMBER = re.compile(r"^\d+(?:\.\d+)*\s*[:.]\s*")
_LIST_NUMBER = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+")
# "28620C", "1000C", "70 GSM Creamwove" -- extraction debris off a diagram.
_MOSTLY_DIGITS = re.compile(r"^[\d\s.,:;/%()\-]*[A-Za-z]{0,2}[\d\s.,:;/%()\-]*$")


def clean_heading(heading: str) -> str:
    """The heading worth putting in the breadcrumb, or "" for junk.

    The breadcrumb ("Class 6 > Science > Frictional force") is prepended to
    every chunk before embedding so a paragraph that has stopped naming its
    subject still carries the chapter's vocabulary. That only helps when the
    heading is really the subject. In the shipped index it frequently is not:
    "28620C", "B", "3. Fill in the blanks with the appropriate", "5. Go toward
    the left and then to the right". Each of those is prepended to real prose
    and pulls the vector towards nothing, or towards the exercise.

    Returning "" is safe -- the breadcrumb falls back to "Class 6 > Science",
    which is still the partition the chunk belongs to.
    """
    text = " ".join((heading or "").split())
    if not text:
        return ""

    # Repeatedly, because the syllabus table numbers sections "06.72.01" and a
    # single pass leaves "01 Identifies materials..." as the topic.
    for _ in range(3):
        stripped = _FIGURE_NUMBER.sub("", text, count=1)
        if stripped == text:
            stripped = _LIST_NUMBER.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    text = text.strip(" .:;-–—")
    if not text:
        return ""

    if _MOSTLY_DIGITS.match(text):          # "28620C", "1000C"
        return ""
    if len(_LETTERS.findall(text)) < 4:     # "B", "E", "lll"
        return ""
    if "?" in text:                         # "What will happen if - ?"
        return ""
    if is_apparatus(text) or _BOX_LABEL.match(text):
        return ""
    if _IMPERATIVE.match(text):             # an activity step, not a heading
        return ""
    words = text.split()
    if len(words) > 8:                      # a wrapped sentence, not a heading
        return ""
    return text
