"""S7 -- the exercise and activity material that must never reach an embedding.

A textbook's exercises are *about* the chapter's topic, so they embed next to
the definition a student is asking for and compete with it. The highest-value
case, measured on 2026-09-16: "What are the poles of a magnet?" retrieved

    (c) There is repulsion between the .......... poles of a magnet, and
        attraction between its ............ poles.

first, and the tutor filled the blanks in backwards and taught the student that
opposite poles repel. That passage outranks the real definition because it is a
near-verbatim copy of it with the answer deleted, so no distance threshold can
separate them.

WHAT CHANGED FROM THE SINGLE-BOOK VERSION

The structure was right and the vocabulary was wrong. Two measured failures:

  * `_BOX_LABEL` matched "exercise" and then demanded end-of-string, so the
    plural "Exercises" -- 12 occurrences in the NCERT books, plus 6 more as
    "EXERCISES" -- never matched. The same anchor made "Activity 1" fail on the
    digit. Both are one-character misses and both are common.
  * `_EXERCISE_STEM` was anchored to the start of a paragraph, so "3. Say if the
    statements given below are right or wrong" did not match "right or wrong",
    and "1. Choose an appropriate word and fill in the blanks" did not match
    "choose the ...". A leaked true/false stem is the dangerous one: the
    suppression run never opens, and the items below it enter the corpus as flat
    assertions of the opposite of what the chapter teaches.

So stems are now searched within the first clause rather than anchored, labels
tolerate a plural and a trailing number, and both lists are seeded with the
vocabulary of BOTH publishers and then extended per book by the profile.

WHAT IS DELIBERATELY KEPT: the "What we have learnt" summaries, whose bulleted
lines are the chapter's own definitions restated compactly; rhetorical questions
inside prose, because the answer is the next sentence; and anything this module
is unsure about. A false positive deletes a fact and no later stage can put it
back; a false negative leaves one noisy line in a chunk. They are not equally
bad.
"""

import re
from typing import List, Optional, Sequence

from .structure import clean_heading, looks_like_heading
from .types import BookProfile

# --------------------------------------------------------------------------
# blanks: the publisher removed the answer
# --------------------------------------------------------------------------
# Four or more dots, or three or more underscores. Body text never does this;
# a contents leader and a blank to be filled both do. Three dots are excluded
# on purpose -- that is an ellipsis. This rule needed no change: it fires on
# every book, and catches NCERT's "Activity ______________ 5.1" as a bonus.
_BLANK_RUN = re.compile(r"\.{4,}|_{3,}|…{2,}")

# --------------------------------------------------------------------------
# box labels: a paragraph that is only a section marker
# --------------------------------------------------------------------------
# Two kinds of label, and the difference decides whether a whole PAGE is
# treated as an exercise. Both are dropped as paragraphs; only the first is
# evidence that the page around it is an exercise.
#
# Conflating them cost a gold answer. "Substances in Daily Use" p.42 carries a
# "Take pieces of wax..." activity box and scores 0.48 density. Counting the box
# label as the page's instruction routed it as an exercise, and
# keep_on_exercise_page then dropped "Read this list of substances : Spirit,
# camphor, petrol, ghee, coconut oil, naphthalene balls..." for opening on an
# imperative -- taking the answer to "which substances sublimate?" with it.
_SECTION_EXERCISE = (
    r"question|exercise|"
    r"answer\s+the\s+following|now\s+answer|"
    r"what\s+(?:we|you)\s+have\s+learnt"
)
_INFO_BOX = (
    # MSCERT
    r"(?:let'?s\s+)?try\s+this|do\s+you\s+know(?:\s+this)?|can\s+you\s+tell|"
    r"can\s+you\s+recall|use\s+your\s+brain\s+power|observe\s+and\s+discuss|"
    r"find\s+out|always\s+remember|science\s+watch|a\s+little\s+fun|"
    r"in\s+the\s+past|think\s+about\s+it|introduction|"
    # NCERT
    r"more\s+to\s+know|group\s+activity|extended\s+learning[\w\s\-]*|"
    r"suggested\s+projects?(?:\s+and\s+activities)?|let\s+us\s+find\s+out|"
    r"keywords?|did\s+you\s+know|speaking|thinking\s+about|"
    # shared
    r"activity|project|discuss"
)
# The plural and a trailing number are what the old anchor got wrong:
# "Exercises" failed on the s, "Activity 1" on the digit.
_TRAILER = r"s?\b[\s.:;!?…\-]*\d*[\s.:;!?…\-]*$"
_SECTION_LABEL = re.compile(r"^(?:{}){}".format(_SECTION_EXERCISE, _TRAILER), re.IGNORECASE)
_BOX_LABEL = re.compile(
    r"^(?:{}|{}){}".format(_SECTION_EXERCISE, _INFO_BOX, _TRAILER), re.IGNORECASE
)

# --------------------------------------------------------------------------
# exercise stems: the instruction that turns what follows into exercise material
# --------------------------------------------------------------------------
_STEM = re.compile(
    r"(?:"
    r"fill\s+in\s+the\s+blank|"
    r"match\s+the\b|"
    r"true\s+o[rf]\s+false|"
    r"right\s+or\s+wrong|"
    r"say\s+if\s+the\s+statements|"
    r"odd\s+one\s+out|who\s+is\s+the\s+odd|"
    r"choose\s+(?:the|an|a)\s+(?:correct|term|proper|appropriate|word)|"
    r"select\s+the\s+(?:correct|proper)|"
    r"write\s+(?:the\s+)?answers?\b|"
    r"answer\s+the\s+following|"
    r"(?:answer|write)\s+in\s+your\s+own\s+words|"
    r"give\s+(?:scientific\s+)?reasons|"
    r"solve\s+the\s+following|"
    r"complete\s+the\s+(?:following|statements|table|sentences)|"
    r"put\s+a\s+.{0,6}\s*mark|tick\s+the\s+correct|"
    r"spot\s+the\s+following|"
    r"draw\s+(?:labelled\s+)?diagrams?\b|"
    r"use\s+the\s+words|words?\s+from\s+the\s+brackets|term\s+from\s+the\s+brackets|"
    r"name\s+(?:them|these|the\s+following)\b|"
    r"what\s+will\s+happen\s+if|why\s+is\s+it\s+said\s+that"
    r")",
    re.IGNORECASE,
)
# How far into a paragraph an instruction may sit and still be the instruction.
# Bounded rather than anchored: reflow splits a stem across lines on a narrow
# column, and NCERT prefixes them ("Say if the statements given below are...").
_STEM_WINDOW = 120
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# A row of a match-the-pairs table: "(2) Oxygen (b) Rain".
_PAIR_ROW = re.compile(r"^\(?\w{1,3}[.)]\s*\S.{0,40}?\(\w{1,3}[.)]\s*\S")
# "(a) ... (b) ... (c) ..." in one paragraph is an answer list, not prose.
_OPTION_MARKER = re.compile(r"\(\s*[a-z0-9]{1,2}\s*\)")
# A numbered exercise question, which reflow often splits before its own mark.
_NUMBERED_QUESTION = re.compile(r"^\(?[0-9ivx]{1,3}[.)]\s+[^.]*\?")
_LETTERS = re.compile(r"[A-Za-z]")


def _flat(text: str) -> str:
    return " ".join((text or "").split())


# The list number an exercise instruction is printed behind. It has to come off
# before the clause is found, because "1." looks exactly like a sentence end --
# which is why "1. Choose an appropriate word..." used to yield the clause "1."
# and match nothing at all.
_LEADING_NUMBER = re.compile(r"^\(?\s*[0-9ivxIVX]{1,3}\s*[.)]\s+")


def _first_clause(text: str) -> str:
    """The opening instruction, if there is one: up to the first sentence end."""
    head = _LEADING_NUMBER.sub("", text[:_STEM_WINDOW], count=1)
    parts = _SENTENCE_SPLIT.split(head, maxsplit=1)
    return parts[0] if parts else head


# A numbered item that opens on an imperative verb. This is the STRUCTURAL form
# of an exercise instruction, and it is here because the phrase list above will
# always have holes: it was widened once for NCERT and still missed "1. Classify
# the following as a lever, a pulley and an inclined plane" and "6. Name the
# levers mentioned in the following passage", which between them put an exercise
# page in front of "What is a lever?" and made the tutor contradict the book.
#
# Numbering is what makes this safe. Body prose uses imperatives freely -- "Take
# a magnet from the laboratory", "Read this list of substances" -- and those are
# left alone; a textbook only numbers a line when it is enumerating a task.
_NUMBERED_IMPERATIVE = re.compile(
    r"^\(?\s*\d{1,3}\s*[.)]\s+"
    r"(?:classify|name|identify|describe|explain|state|define|list|match|choose|"
    r"select|complete|fill|write|draw|solve|find|give|answer|say|arrange|label|"
    r"distinguish|differentiate|compare|calculate|observe|spot|tick|underline)\b",
    re.IGNORECASE,
)
# Long enough to be a passage rather than an instruction.
_MAX_INSTRUCTION_CHARS = 300


def is_stem(paragraph: str) -> bool:
    """The paragraph opens with an exercise instruction."""
    text = _flat(paragraph)
    if _STEM.search(_first_clause(text)):
        return True
    return bool(_NUMBERED_IMPERATIVE.match(text)) and len(text) <= _MAX_INSTRUCTION_CHARS


def is_box_label(paragraph: str, profile: Optional[BookProfile] = None) -> bool:
    """The whole paragraph is a marker of any kind and says nothing."""
    text = _flat(paragraph)
    if not text:
        return False
    if _BOX_LABEL.match(text):
        return True
    return bool(profile and text in profile.labels)


def is_exercise_marker(paragraph: str) -> bool:
    """This paragraph says the material around it is an exercise.

    Narrower than `is_box_label` on purpose -- "QUESTIONS" and "Exercises" mark
    an exercise section, while "Try this." and "Do you know ?" mark an activity
    or an aside sitting inside a perfectly ordinary lesson page. Only the first
    kind may route a whole page. See the note above _SECTION_EXERCISE for the
    gold answer that conflating them cost.
    """
    text = _flat(paragraph)
    return bool(text) and (bool(_SECTION_LABEL.match(text)) or is_stem(text))


def is_apparatus(paragraph: str, profile: Optional[BookProfile] = None) -> bool:
    """True for a paragraph that is exercise or activity furniture."""
    text = _flat(paragraph)
    if not text:
        return False
    if _BLANK_RUN.search(text):
        return True
    if is_box_label(text, profile):
        return True
    if is_stem(text):
        return True
    if _PAIR_ROW.match(text) and len(text) < 120:
        return True
    if len(_OPTION_MARKER.findall(text)) >= 3:
        return True
    if _NUMBERED_QUESTION.match(text) and len(text) < 100:
        return True
    return False


def _is_exercise_item(text: str) -> bool:
    """A lettered or numbered item belonging to the stem above it.

    Two shapes, because reflow splits the stem itself on a narrow column: the
    items do not always start with their own marker. Both are length-capped and
    both apply only while a stem is open, so a definition given as a numbered
    point is untouched.
    """
    if len(text) > 300:
        return False
    if re.match(r"^\(?[a-z0-9]{1,2}[.)]\s", text, re.IGNORECASE) and len(text) <= 200:
        return True
    return len(_OPTION_MARKER.findall(text)) >= 2


def strip_apparatus(
    paragraphs: Sequence[str], profile: Optional[BookProfile] = None
) -> List[str]:
    """The paragraphs of a lesson page worth embedding, in order.

    A stem suppresses the short lettered items after it, which is what removes
    the true/false statements that assert the opposite of what the chapter
    teaches. The run ends at the first paragraph that is neither an item nor
    apparatus, so it cannot escape into the next section's prose.
    """
    out: List[str] = []
    in_exercise = False
    for para in paragraphs:
        text = _flat(para)
        if not text:
            continue
        if is_stem(text):
            in_exercise = True
            continue
        if is_apparatus(text, profile):
            if is_box_label(text, profile):
                in_exercise = False      # a label separates one block from the next
            continue
        if in_exercise and (_is_exercise_item(text) or len(text) < 80):
            continue
        in_exercise = False
        out.append(para)
    return out


def exercise_density(
    paragraphs: Sequence[str], profile: Optional[BookProfile] = None
) -> float:
    """Share of a page's paragraphs that are exercise apparatus."""
    flat = [_flat(p) for p in paragraphs]
    flat = [p for p in flat if p]
    if not flat:
        return 0.0
    bad = sum(
        1 for p in flat
        if is_apparatus(p, profile) or is_stem(p) or _OPTION_MARKER.findall(p)
    )
    return bad / len(flat)


def page_is_exercise(
    paragraphs: Sequence[str], ratio: float = 0.40, profile: Optional[BookProfile] = None
) -> bool:
    """True for a page that is an exercise, not a lesson.

    Two conditions, because either alone misfires. Density catches the page;
    requiring an explicit instruction stops a legitimate page of worked examples
    or a figure table -- full of "(a)" markers and no instructions -- going with
    it. The stem requirement is what makes 0.40 safe, and it is also what
    collapsed on NCERT until the vocabulary was widened: Class 10 Science routed
    1 page of 274 while 31 were dense enough and carried no recognised stem.
    """
    if exercise_density(paragraphs, profile) < ratio:
        return False
    return any(is_exercise_marker(p) for p in paragraphs)


def keep_on_exercise_page(
    paragraphs: Sequence[str], profile: Optional[BookProfile] = None
) -> List[str]:
    """The prose worth keeping from a page that is otherwise an exercise.

    Dropping such a page whole was the first version of this and it was wrong:
    the end-of-chapter exercise shares its page with the chapter summary, and
    those lines are the densest definitions in the book. Measured on the MSCERT
    book, dropping the twelve exercise pages outright removed 20 declarative
    summary lines that appear nowhere else -- including "A diet containing all
    nutrients in the right quantity is called a balanced diet".

    So the page is filtered hard rather than deleted. A paragraph survives only
    if it states something.
    """
    from .structure import _IMPERATIVE

    out: List[str] = []
    bullets = sorted((profile.bullets if profile else set()), key=len, reverse=True)
    for para in paragraphs:
        text = _flat(para)
        if not text or is_apparatus(text, profile) or is_stem(text):
            continue
        if _OPTION_MARKER.search(text):
            continue
        body = text
        for token in bullets:
            if body.startswith(token + " "):
                body = body[len(token) + 1:]
                break
        else:
            body = re.sub(r"^[l•●·]\s+", "", body)
        if _IMPERATIVE.match(body):
            continue
        if body.rstrip().endswith("?"):
            continue
        if len(body.split()) < 4:
            # A heading is short by nature; keep it only if it survives
            # validation, so an exercise heading still goes.
            if looks_like_heading(body, profile) and clean_heading(body, profile):
                out.append(body)
            continue
        out.append(body)
    return out


def is_question_only(text: str) -> bool:
    """True when nothing in this text states anything.

    Whole-chunk test, applied after merging, so a rhetorical question inside
    prose is safe -- its chunk has plenty of declarative sentences around it.
    """
    flat = _flat(text)
    if not flat:
        return True
    sentences = [s for s in _SENTENCE_SPLIT.split(flat) if len(s.strip()) > 3]
    if not sentences:
        return True
    return all(s.rstrip().endswith("?") for s in sentences)
