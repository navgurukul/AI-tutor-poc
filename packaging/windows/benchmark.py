"""Core latency and grounding numbers, measured on the device itself.

The frontend already logs [timing] lines to the browser console, but those need
DevTools open and a person watching. This runs the same path headlessly so a
laptop can be checked during provisioning, and two machines can be compared.

    "C:\\Program Files\\AITutor\\runtime\\python\\python.exe" benchmark.py

    benchmark.py --label exp004 --repeat 3
    benchmark.py --topics 3               # first 3 topics only, for a quick look
    benchmark.py http://127.0.0.1:8757 --label multilang
    benchmark.py --retrieval-only         # answer key only, no generation: seconds

Every turn is also appended to benchmarks.csv in the log directory, beside the
turns-*.csv the backend writes. Rows carry the same turn_id the backend logged,
so a benchmark run joins straight onto turns-backend.csv:

    turn_id -> prompt_tokens, prefill_ms, generation_ms, context_chars

And each run writes a readable transcript, benchmark-<label>-<run_id>.md, with
every answer printed under the pages it cited -- so whether an answer is
actually grounded can be checked against the book, not just inferred from a
distance score.

WHAT THIS MEASURES, and why it is shaped this way
-------------------------------------------------
Questions are grouped into THREADS: a topic question, then a follow-up that
cannot stand on its own ("Why does it change length during the day?"). Each
thread runs down ONE session, so the follow-up carries history exactly as a
student's would. Two separate things are then visible per turn:

  latency    history is re-read through prefill on every turn, so a run that
             opens a fresh session per question reports a number nobody
             experiences -- measured 2.4s optimistic on the target.

  drift      every follow-up contains a dangling pronoun (it, they, this...),
             which is the one case retrieval cannot handle: the topic is in the
             previous turn, not in the sentence, so the vector lands wherever
             the leftover words point. The report shows the page each turn
             retrieved, so a follow-up that wandered into another chapter is
             visible rather than being averaged into a median.

  answer     every question has an ANSWER KEY: a phrase from the book that
             the passage answering it contains. Each turn is also searched
             through /api/library/search, the same retrieval without the
             model, and scored on where the answer passage ranked and whether
             it reached the prompt. Ranked is not enough -- the character
             budget regularly cuts the second passage, and in exp004 that is
             how the magnet-pole definition was cited but never read. The page
             distance above is a proxy for this; the key is the measurement.

Timings are medianed over GROUNDED turns only. An ungrounded turn carries no
excerpts, so it prefills ~130 tokens instead of ~650 and finishes in a fifth of
the time -- averaging it in reports a speed the tutor never delivers.

Numbers that matter on a CPU-only device:
  ttft   time to first token -- what a student actually waits for
  ptok   prompt tokens Ollama had to read before writing anything
  src    passages retrieved (0 = the answer was ungrounded)
  page   where the top passage came from -- the drift signal

Unlike the backend's turn logs, this one records the question text. These are
fixed strings authored here, not anything a student typed, so the rule that
keeps child-entered text out of the logs is not in play.
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE = "http://127.0.0.1:8756"

# Ten topics from the shipped corpus -- General Science, Class 6, Maharashtra
# State Bureau -- with the chapter each should retrieve. Taken off the book's
# own contents rather than invented, because an off-syllabus question measures
# nothing: it retrieves no excerpts, prefills a fifth of the tokens, and the
# model answers thinly from its own knowledge. Four of the six questions in the
# 10 Sep UI log were Class 8-9 material, which is most of why the replies there
# looked short.
#
# Spread is deliberate. A question whose excerpts fill the 1200-char budget
# costs roughly four times one whose excerpts are short (measured on target:
# 537 chars -> 3.4s to first token, 1239 chars -> 12.5s, same top_k, same
# code), so a set clustered at one end would describe the device badly.
#
# The second entry in each thread is the actual test. Every one carries a
# dangling pronoun, so the topic lives in the previous turn and not in the
# sentence -- the case a distance threshold cannot catch, because a question
# with no content is a mediocre match for everything and the distances look
# healthy. rag/followup.py (ported from the multilingual branch) carries the
# topic question into the search for exactly these; RAG_CARRY_FOLLOWUPS=0 on
# the backend turns it off, which is how to A/B it with this script.
THREADS = [
    # (topic question, follow-up that cannot stand alone, expected chapter)
    ("What is a shadow?",
     "Why does it change length during the day?",         "Light"),
    ("What is frictional force?",
     "How can we reduce it?",                             "Force"),
    ("What is gravitational force?",
     "Which direction does it act in?",                   "Force"),
    ("What is sublimation?",
     "Which substances do this?",                         "States of matter"),
    # The book says "solid, liquid and gaseous state" (p.42); "three states of
    # matter" appears nowhere in it. Embeddings bridge the gap, but matching
    # the source's own wording is what the retrieval is being asked to do.
    ("What are the solid, liquid and gaseous states?",
     "How do they change from one to another?",           "States of matter"),
    ("What is a lever?",
     "Where is its fulcrum?",                             "Simple machines"),
    ("How is sound produced?",
     "How does it reach our ears?",                       "Sound"),
    ("What are the poles of a magnet?",
     "What happens when we bring two of them together?",  "Magnets"),
    ("What are the types of joints in our body?",
     "Which of these is in the elbow?",                   "Skeletal system"),
    ("What is a balanced diet?",
     "Why do we need it?",                                "Nutrition"),
]

# SET A -- standalone questions, one per fresh session, no follow-up. THREADS
# above is set B.
#
# Different chapters from set B on purpose, not the same topic questions asked
# again: set B's first turns are already standalone (a fresh session each), so
# re-asking them here would measure the same thing twice. Between them the two
# sets touch 13 of the book's 16 chapters. This set measures grounding with
# nothing to lean on but the excerpts -- no history, no carried query -- which
# is the cleanest read of what a budget cut costs.
STANDALONE = [
    # (question, chapter)
    ("What are the atmosphere, hydrosphere and lithosphere?", "Natural resources"),
    ("What are the characteristics of living things?",        "The living world"),
    ("What is a disaster?",                                   "Disaster management"),
    ("What first aid should be given for a snakebite?",       "Disaster management"),
    ("How is paper made from wood?",                          "Substances in daily use"),
    ("Why does our skin sweat?",                              "Skin"),
    ("What is linear motion?",                                "Motion"),
    ("When is work said to be done?",                         "Work and energy"),
    ("What are conventional energy sources?",                 "Work and energy"),
    ("Which are the inner planets?",                          "The universe"),
]

# The character budgets to sweep. The top passage is always kept whatever the
# budget -- it only decides whether passage #2 fits -- so on this book's chunk
# sizes (median 340 chars, p75 726, max 1201) each step moves roughly a tenth of
# turns from two passages to one: an estimated 68% / 58% / 46% keep both at
# 1200 / 1000 / 800. What is being measured is one passage versus two, more
# than a character count.
DEFAULT_BUDGETS = (1200, 1000, 800)

# Run once at the end, reported, and NEVER counted in the timings. An
# off-syllabus question is a correctness check -- the distance gate should
# abstain and return zero sources -- and its latency is meaningless next to a
# grounded turn: no excerpts means ~130 prompt tokens against ~650, which
# dragged the reported median from 7.6s down to 4.4s when it was in the set.
ABSTAIN_CHECK = "Who won the 2022 football world cup?"

# What a correct passage must contain, per question: phrases copied from the
# book (PDF page in the comment; the printed page is ten lower). A retrieved
# passage answers the question if its heading or text contains any of them,
# compared lower-cased with whitespace collapsed -- the extractor breaks lines
# mid-sentence.
#
# Phrases, not chunk ids, on purpose: ids are reassigned by every re-ingest,
# and re-chunking is one of the fixes this key exists to measure. A phrase
# only breaks if the book changes.
#
# Strict by design. "What is frictional force?" retrieving the chunk headed
# "5. Frictional force" does NOT count: on this PDF that chunk opens with the
# electrostatic-force column, and the definition lives in the chunk before it.
ANSWER_KEY = {
    "What is a shadow?": ["this dark part is called"],                    # p.111
    "Why does it change length during the day?": [
        "long in the mornings and evenings"],                             # p.111
    "What is frictional force?": [
        "force of friction comes into play",
        "always acts against the direction of motion"],                   # p.83
    "How can we reduce it?": [
        "oil or lubricant is released",                                   # p.99
        "friction between them is less"],                                 # p.83
    "What is gravitational force?": [
        "force applied by the earth to pull objects towards itself",
        "earth pulls all the objects towards itself"],                    # p.81
    "Which direction does it act in?": [
        "earth pulls all the objects towards itself",
        "force applied by the earth to pull objects towards itself",
        "opposite to that of an object moving upwards"],                  # p.81
    "What is sublimation?": [
        "directly into a gas or vapour without first changing into a liquid"],  # p.46
    "Which substances do this?": [
        "naphthalene balls",                                              # p.42
        "iodine crystals do not melt"],                                   # p.46
    "What are the solid, liquid and gaseous states?": [
        "has a shape of its own"],                                        # p.43
    "How do they change from one to another?": [
        "on gaining heat the substance changes"],                         # p.42-43
    "What is a lever?": [
        "such a machine is called a lever",
        "a lever has three parts"],                                       # p.96
    "Where is its fulcrum?": [
        "the lever rotates about the fulcrum",                            # p.96
        "the fulcrum is in the centre",                                   # p.97
        "the fulcrum on one side"],                                       # p.97
    "How is sound produced?": [
        "vibration of an object is necessary for the production of sound",
        "in other words, they vibrate"],                                  # p.102
    "How does it reach our ears?": ["the sound waves reach our ears"],    # p.103
    "What are the poles of a magnet?": [
        "points to the north is called the north pole"],                  # p.117
    "What happens when we bring two of them together?": [
        "repulsion between like poles"],                                  # p.118
    "What are the types of joints in our body?": [
        "joints are of two types"],                                       # p.71
    "Which of these is in the elbow?": ["the elbow and knee joints"],     # p.71
    "What is a balanced diet?": ["is called a balanced diet"],            # p.63
    "Why do we need it?": ["significance of a balanced diet"],            # p.63
    # --- set A, standalone ---------------------------------------------------
    "What are the atmosphere, hydrosphere and lithosphere?": [
        "called the earth's atmosphere, hydrosphere and lithosphere"],      # p.11
    "What are the characteristics of living things?": [
        "characteristics of living things"],                              # p.19
    # The book itself misspells it "distaster" on this page, so the key keys on
    # the rest of the definition rather than on the word.
    "What is a disaster?": [
        "causes large scale damage to life, property"],                   # p.36
    "What first aid should be given for a snakebite?": [
        "tie a cloth tightly above the wound",
        "wash the wound with water"],                                     # p.40
    "How is paper made from wood?": ["it helps to form pulp"],            # p.56
    "Why does our skin sweat?": ["glands which secrete sweat"],           # p.71
    "What is linear motion?": [
        "this motion of an object is called linear motion"],              # p.75
    "When is work said to be done?": ["work is said to be done"],         # p.85
    "What are conventional energy sources?": [
        "called conventional energy sources"],                            # p.91
    "Which are the inner planets?": [
        "venus, earth and mars are the inner planets"],                   # p.124
}

# How deep to look for the answer passage. Past the gate nothing comes back
# anyway, so this only bounds the report.
ANSWER_SEARCH_K = 20

# A follow-up landing this many pages from its topic question is in a different
# chapter of this book. Reported, not enforced -- the page numbers are printed
# either way, because a threshold is a summary and the pages are the evidence.
DRIFT_PAGES = 12

FIELDS = (
    "ts_utc",
    "run_id",           # one per invocation, so runs never blur together
    "label",            # --label exp004, --label topk2 ...
    "set_name",         # A = standalone, B = threads with pronoun follow-ups
    "budget",           # context_max_chars sent for this turn
    "pass_no",          # 1-based, with --repeat; 0 marks the abstain check
    "thread_no",
    "turn_in_thread",   # 1 = topic question, 2 = the pronoun follow-up
    "is_followup",
    "question",
    "expected_chapter",
    "turn_id",          # joins to turns-backend.csv
    "session_id",
    "ttft_ms",          # measured here, client-side: retrieval + prefill
    "total_ms",
    "answer_chars",
    "chars_per_second",
    "sources",
    "top_page",         # where the best passage came from -- the drift signal
    "top_heading",
    "top_distance",
    "source_pages",     # every page cited, so a claim can be checked against all of them
    "drift_pages",      # follow-ups only: pages away from its topic question
    "query_carried",    # 1 = searched with the previous question in front
    "answer_rank",      # where the answer-key passage ranked; blank = not retrieved
    "answer_in_prompt", # 1 = an answer-key phrase is in the text the model read
    "context_chars",    # excerpt text actually sent, after the budget
    "passages_read",    # how many passages survived the budget -- 0, 1 or 2
    "excerpt_overlap",  # share of the answer's content words found in what it read
    "prompt_tokens",    # the rest come from Ollama, via the done frame's usage
    "prefill_ms",
    "completion_tokens",
    "generation_ms",
    "tokens_per_second",
    "load_ms",
    "model",
    "base_url",
    # Last on purpose. A reply runs several hundred characters and would push
    # every number off the screen in a spreadsheet; at the end it can simply be
    # collapsed. The readable version is the transcript written beside this.
    "answer",
    "context",          # the excerpt block the model read -- what to grade it against
)


def resolve_log_dir(explicit):
    """Where benchmarks.csv lands, matching the backend's own log directory.

    AITUTOR_LOG_DIR is what the launcher sets for the *backend* process, so it
    is usually absent from the shell a person runs this from -- hence the
    ProgramData fallback, which is the same path launch.ps1 computes.
    """
    if explicit:
        return Path(explicit)
    configured = os.environ.get("AITUTOR_LOG_DIR", "").strip()
    if configured:
        return Path(configured)
    program_data = os.environ.get("ProgramData", "").strip()
    if program_data:
        candidate = Path(program_data) / "AITutor" / "logs"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent / "logs"


def append_rows(log_dir, rows):
    """One append per run. Never fatal: a benchmark that printed its numbers
    has done its job even if the disk refused the copy."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "benchmarks.csv"
        # A file written by an older version of this script has different
        # columns. Appending under its header silently shifts every value one
        # or more places to the right -- it happened once, when threads were
        # added, and the numbers still looked plausible. So an existing file
        # whose header does not match is set aside, never appended to.
        if path.exists():
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                existing = next(csv.reader(fh), [])
            if existing != list(FIELDS):
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                retired = path.with_name(f"benchmarks-old-{stamp}.csv")
                path.rename(retired)
                print(f"\n  benchmarks.csv had an older column layout; "
                      f"moved it to {retired.name}")
        new = not path.exists()
        # utf-8-sig: a byte-order mark, which is what makes Excel and older
        # Notepad read this as UTF-8 rather than Windows-1252. Without it every
        # curly quote in a model reply arrived as mojibake. Python writes the
        # mark once, at the start of a new file, and not again on append.
        with path.open("a", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(FIELDS), extrasaction="ignore")
            if new:
                writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in FIELDS})
        return path
    except OSError as exc:
        print(f"\n  could not write benchmarks.csv: {exc}")
        return None


def _cited(citations):
    """'p.108 Light (0.31) · p.110 (0.35)' -- each page the answer rests on."""
    out = []
    for c in citations:
        dist = c.get("distance")
        dist = f" ({dist:.2f})" if isinstance(dist, (int, float)) else ""
        head = (c.get("heading") or "").strip()
        head = f" {head[:40]}" if head else ""
        out.append(f"p.{c.get('page_start', '?')}{head}{dist}")
    return " \u00b7 ".join(out) if out else "no passages retrieved -- answered from the model alone"


def _norm(text):
    """Lower-case, straight quotes, whitespace collapsed: how the answer key
    is compared, since the extractor breaks lines mid-sentence."""
    text = (text or "").replace("’", "'").replace("‘", "'")
    return " ".join(text.split()).lower()


def passages_in(context):
    """How many excerpts reached the prompt. build_context_block labels each one
    "[n] Title - heading - p. N" at the start of a line, so counting the labels
    counts the passages -- the number `sources` overstates whenever the budget
    cut the second one."""
    if not context:
        return 0
    return sum(1 for line in context.splitlines()
               if line[:1] == "[" and "]" in line[:5] and line[1:line.index("]")].isdigit())


def answer_in_context(question, context):
    """True if an answer-key phrase is in the text the model actually read.

    The budget-correct version of score_retrieval's answer_in_prompt, which is
    computed by the library search against the SITE budget and so is wrong for
    every other arm of a sweep. None when there is no key, or no context to
    look in (a backend too old to return it)."""
    phrases = [_norm(p) for p in ANSWER_KEY.get(question, [])]
    if not phrases or context is None:
        return None
    haystack = _norm(context)
    return any(p in haystack for p in phrases)


# Words too common to say anything about where an answer came from.
_STOP = set("""
a about above after again against all also am an and any are as at be because
been before being below between both but by can could did do does doing down
during each few for from further had has have having he her here hers him his
how i if in into is it its itself just let like made make many may me more most
much must my no nor not now of off on once one only or other our out over own
same she should so some such than that the their them then there these they
this those through to too under until up upon us very was we were what when
where which while who whom why will with would you your also called such used
use using example examples imagine think student students think further
""".split())


def _content_words(text):
    words = "".join(ch if ch.isalpha() else " " for ch in _norm(text)).split()
    return {w for w in words if len(w) >= 4 and w not in _STOP}


def excerpt_overlap(answer, context):
    """Share of the answer's content words that also appear in what it read.

    A triage signal, not a verdict. High overlap says the answer is built from
    the excerpts; low overlap says it came from somewhere else -- which is how
    the 11 Sep joints answer looks (best retrieval of the run, 0.16, and a
    reply in anatomy-textbook categories the page never uses). It cannot see
    whether the words were put together correctly: "like poles attract" scores
    as well as "like poles repel". Deliberately not an LLM judge, which would
    cost another full generation of the time being measured. None when there
    was nothing to read.
    """
    if not context:
        return None
    said = _content_words(answer)
    if not said:
        return None
    return round(len(said & _content_words(context)) / len(said), 2)


def score_retrieval(base, question, previous_question=None):
    """Where the answer passage ranked for this question, without the model.

    Asks /api/library/search, which runs the same retrieval a chat turn does --
    given the previous question, the same carrying too. Returns the 1-based
    rank of the first hit containing an answer-key phrase (None if none within
    the gate), whether that hit reaches the prompt, and whether the search was
    carried. The last two are None against a backend too old to report them.
    """
    out = {"answer_rank": None, "answer_in_prompt": None, "query_carried": None,
           "answer_page": None, "answer_distance": None, "keyed": False}
    phrases = [_norm(p) for p in ANSWER_KEY.get(question, [])]
    if not phrases:
        return out
    out["keyed"] = True
    body = {"question": question, "k": ANSWER_SEARCH_K}
    if previous_question:
        body["previous_question"] = previous_question
    req = urllib.request.Request(
        f"{base}/api/library/search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            found = json.load(resp)
    except Exception as exc:                       # noqa: BLE001
        print(f"    answer key: search failed for \"{question}\": {exc}")
        return out
    hits = found.get("hits") or []
    excerpts = found.get("excerpts") or []
    in_prompt = found.get("in_prompt")
    # What each in-prompt passage is sent as, once shortened to the question.
    sent = found.get("prompt_excerpts")
    if "query_carried" in found:
        out["query_carried"] = bool(found["query_carried"])
    for i, (hit, text) in enumerate(zip(hits, excerpts)):
        haystack = _norm(f"{hit.get('heading') or ''} {text}")
        if any(p in haystack for p in phrases):
            out["answer_rank"] = i + 1
            out["answer_page"] = hit.get("page_start")
            out["answer_distance"] = hit.get("distance")
            if isinstance(in_prompt, list) and i < len(in_prompt):
                out["answer_in_prompt"] = bool(in_prompt[i])
            break
    else:
        # Not retrieved at all is a definite no, even on an old backend.
        out["answer_in_prompt"] = False
    if out["answer_rank"] is not None and isinstance(sent, list):
        # A passage can reach the prompt with its answer sentence shortened
        # away, so "in the prompt" has to mean the phrase is in what is sent.
        out["answer_in_prompt"] = any(
            text is not None
            and any(p in _norm(f"{hit.get('heading') or ''} {text}") for p in phrases)
            for hit, text in zip(hits, sent)
        )
    return out


def answer_label(score):
    """'#1 read', '#2 cut', '#3', 'missed' -- the answer key, compactly."""
    if not score.get("keyed"):
        return ""
    rank = score.get("answer_rank")
    if rank is None:
        return "missed"
    read = score.get("answer_in_prompt")
    tag = " read" if read else (" cut" if read is False and rank <= 2 else "")
    if read is None:
        tag = " ?"
    return f"#{rank}{tag}"


def answer_sentence(score):
    """The transcript's version: where the answer passage was, and whether the
    model ever saw it."""
    if not score.get("keyed"):
        return ""
    carried = {True: " Searched with the previous question in front.",
               False: "", None: ""}[score.get("query_carried")]
    rank = score.get("answer_rank")
    if rank is None:
        return (f"**Answer key:** the answer passage was not retrieved "
                f"(not in the top {ANSWER_SEARCH_K} inside the gate).{carried}")
    where = f"p.{score.get('answer_page')}"
    dist = score.get("answer_distance")
    if isinstance(dist, (int, float)):
        where += f" ({dist:.2f})"
    read = score.get("answer_in_prompt")
    if read:
        fate = "and it reached the prompt"
    elif score.get("answer_shortened"):
        fate = ("and the passage reached the prompt, but shortening it to the "
                "question cut the answer out")
    elif read is False:
        fate = ("but the character budget cut it before the prompt" if rank <= 2
                else "below the passages that reach the prompt")
    else:
        fate = "(this backend does not report whether it reached the prompt)"
    return f"**Answer key:** answer passage ranked #{rank}, {where}, {fate}.{carried}"


def write_transcript(log_dir, run_id, label, model, base, rows):
    """Every question, answer and cited page, readable beside the textbook.

    benchmarks.csv answers "how fast"; this answers "is it right". A reply that
    cites p.108 has only been grounded if what it says is on p.108, and no
    column can check that -- a person with the book open can, in a minute per
    turn. So each answer sits directly under the pages it claims, with the
    retrieval distance beside each (lower is closer; the gate admits <= 0.42).

    One file per run, named by label and run_id so runs never overwrite each
    other. Never fatal, for the same reason the CSV append is not.
    """
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        stem = f"benchmark-{label}-{run_id}" if label else f"benchmark-{run_id}"
        path = log_dir / f"{stem}.md"
        lines = [
            f"# Benchmark {run_id}" + (f" \u2014 {label}" if label else ""),
            "",
            f"{rows[0]['ts_utc'] if rows else ''} \u00b7 {model} \u00b7 {base}",
            "",
            "Check each answer against the pages listed under it. Distance is "
            "retrieval confidence: lower is closer, and the gate admits up to 0.42. "
            "A follow-up marked DRIFT retrieved from a different chapter than its "
            "topic question.",
        ]
        current = None
        for r in rows:
            key = (r.get("set_name"), r.get("budget"), r["pass_no"], r["thread_no"])
            if r["pass_no"] == 0:
                lines += ["", "---", "",
                          "## Retrieval gate check (should retrieve nothing)", "",
                          "*Passing means no textbook page was misused. It does not "
                          "mean the reply is right -- read it.*"]
            elif key != current:
                current = key
                pass_tag = f" \u00b7 pass {r['pass_no']}" if any(
                    x["pass_no"] > 1 for x in rows) else ""
                where = ""
                if r.get("set_name") in ("A", "B"):
                    where = (f" \u00b7 set {r['set_name']}"
                             + (f" \u00b7 {r['budget']} chars" if r.get("budget") else ""))
                lines += ["", "---", "",
                          f"## {r['thread_no']}. {r['expected_chapter']}{where}{pass_tag}"]
            marker = "\u2514 " if r["is_followup"] else ""
            lines += ["", f"### {marker}{r['question']}", ""]
            meta = (f"ttft {r['ttft_ms'] / 1000:.2f}s \u00b7 "
                    f"{r['prompt_tokens'] or '?'} prompt tok \u00b7 "
                    f"{r['answer_chars']} chars")
            if isinstance(r.get("drift_pages"), int):
                flag = " \u2014 **DRIFT**" if r["drift_pages"] > DRIFT_PAGES else ""
                meta += f" \u00b7 {r['drift_pages']} pages from topic{flag}"
            # Two trailing spaces: a Markdown line break, so the citations, the
            # answer key and the timings stay on lines of their own.
            lines += [f"**Cited:** {_cited(r.get('_citations') or [])}  "]
            key_line = answer_sentence(r.get("_score") or {})
            if key_line:
                lines.append(key_line + "  ")
            lines += [f"*{meta}*", "",
                      r["answer"] or "*(empty reply)*"]
        # BOM for the same reason as the CSV: Windows viewers otherwise read
        # it as Windows-1252, and "\u2014" and "\u00b7" became "\u00e2\u0080\u0094".
        path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
        return path
    except OSError as exc:
        print(f"\n  could not write the transcript: {exc}")
        return None


# ---------------------------------------------------------------------------
# The grading sheet
# ---------------------------------------------------------------------------
# Everything needed to judge an answer, in one file that opens offline in any
# browser: the question, what the book says (the answer key), the excerpt text
# the model actually read at each budget, and the answer it gave -- side by
# side across budgets, with a verdict to record for each. Scores save in the
# browser as you go and export as CSV.
#
# Data goes in as JSON and is rendered with textContent, never innerHTML, so no
# answer or excerpt can break the page however odd its characters are.

_EVAL_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grounding review</title>
<style>
:root{--bg:#f4f5f2;--card:#fff;--ink:#1a1f1c;--mute:#5f6b64;--line:#d9ddd6;
--soft:#eceee9;--ok:#1d7a4f;--okbg:#e3f3ea;--warn:#9a6a00;--warnbg:#fbf0d4;
--bad:#b3261e;--badbg:#fbe4e1;--acc:#2f5d8a;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media(prefers-color-scheme:dark){:root{--bg:#121513;--card:#1b1f1d;--ink:#e6ebe7;
--mute:#98a39c;--line:#2f3632;--soft:#232826;--ok:#5fc596;--okbg:#17301f;
--warn:#e0b04a;--warnbg:#2e2510;--bad:#f08a80;--badbg:#341716;--acc:#8fb6de}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:28px 22px 80px}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--mute);font-size:13px;margin-bottom:18px}
.how{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:12px 16px;margin-bottom:18px;font-size:13.5px}
.how b{font-weight:600}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);
display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
button,select{font:inherit;font-size:13px;padding:6px 11px;border:1px solid var(--line);border-radius:5px;
background:var(--card);color:var(--ink);cursor:pointer}
button:hover{border-color:var(--acc)}
.prog{margin-left:auto;font-size:13px;color:var(--mute);font-variant-numeric:tabular-nums}
.tw{overflow-x:auto;margin-bottom:22px}
table{border-collapse:collapse;width:100%;font-size:13px;background:var(--card);border:1px solid var(--line)}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
th{background:var(--soft);font-weight:600;font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--mute)}
td:first-child,th:first-child{text-align:left}
.item{background:var(--card);border:1px solid var(--line);border-radius:6px;margin-bottom:16px}
.ihead{padding:12px 16px 10px;border-bottom:1px solid var(--line)}
.tag{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;
padding:2px 7px;border-radius:3px;background:var(--soft);color:var(--mute);margin-right:6px}
.tag.fu{background:var(--warnbg);color:var(--warn)}
.q{font-size:16.5px;font-weight:600;margin:6px 0 2px}
.after{font-size:13px;color:var(--mute)}
.key{font-size:13px;margin-top:6px}
.key span{font-family:var(--mono);font-size:12.5px;background:var(--soft);padding:1px 5px;border-radius:3px}
.arms{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr))}
.arm{padding:12px 16px 14px;border-right:1px solid var(--line);min-width:0;display:flex;flex-direction:column;gap:8px}
.arm:last-child{border-right:0}
.bud{font-weight:700;font-size:13px}
.chips{display:flex;flex-wrap:wrap;gap:5px}
.chip{font-size:11.5px;padding:2px 7px;border-radius:3px;background:var(--soft);color:var(--mute);font-variant-numeric:tabular-nums}
.chip.ok{background:var(--okbg);color:var(--ok)}.chip.bad{background:var(--badbg);color:var(--bad)}
.chip.warn{background:var(--warnbg);color:var(--warn)}
.ans{white-space:pre-wrap;font-size:14px}
details{font-size:12.5px}summary{cursor:pointer;color:var(--acc)}
pre{white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:12px;background:var(--soft);
padding:9px;border-radius:4px;margin:6px 0 0;max-height:360px;overflow:auto}
mark{background:var(--okbg);color:var(--ok);padding:0 2px;border-radius:2px}
.vrow{display:flex;align-items:center;gap:6px;font-size:12.5px;flex-wrap:wrap}
.vrow .lab{width:74px;color:var(--mute)}
.vrow label{display:inline-flex;align-items:center;gap:3px;padding:3px 8px;border:1px solid var(--line);
border-radius:4px;cursor:pointer;user-select:none}
.vrow input{position:absolute;opacity:0;pointer-events:none}
.vrow input:focus-visible+span{outline:2px solid var(--acc);outline-offset:2px}
.vrow label:has(input[value=y]:checked){background:var(--okbg);border-color:var(--ok);color:var(--ok)}
.vrow label:has(input[value=p]:checked){background:var(--warnbg);border-color:var(--warn);color:var(--warn)}
.vrow label:has(input[value=n]:checked){background:var(--badbg);border-color:var(--bad);color:var(--bad)}
.note{width:100%;font:inherit;font-size:12.5px;padding:5px 7px;border:1px solid var(--line);border-radius:4px;
background:var(--card);color:var(--ink)}
.empty{color:var(--mute);font-style:italic}
.gate{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:14px 16px}
@media(max-width:900px){.arms{grid-template-columns:1fr}.arm{border-right:0;border-bottom:1px solid var(--line)}}
</style></head><body><div class="wrap">
<h1 id="title">Grounding review</h1><div class="sub" id="sub"></div>
<div class="how"><b>Grounded</b> means every claim in the answer is supported by the excerpt text shown
under it &mdash; what the model actually read at that budget, not every page that was cited.
<b>Correct</b> means the answer is right by the book, whatever it read. The two differ: an answer can be
correct from the model's own knowledge while ignoring the excerpt, or faithful to an excerpt that was the wrong
page. <b>Book says</b> is the answer key, copied from the textbook; highlighted where it appears in an excerpt.
<b>Overlap</b> is a word-level hint only &mdash; it cannot tell "like poles repel" from "like poles attract".
Scores save in this browser automatically.</div>
<div class="tw"><table id="summary"></table></div>
<div class="bar"><select id="filter"><option value="all">All sets</option>
<option value="A">Set A &middot; standalone</option><option value="B">Set B &middot; follow-ups</option></select>
<select id="show"><option value="all">All items</option><option value="todo">Not yet scored</option></select>
<button id="export">Export scores (CSV)</button><button id="clear">Clear scores</button>
<span class="prog" id="prog"></span></div>
<div id="items"></div><div class="gate" id="gate"></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
const D=JSON.parse(document.getElementById('data').textContent);
const KEY='grounding-review:'+D.run_id;
let S={};try{S=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}};
const el=(t,c,txt)=>{const e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e};
const B=D.budgets;
document.getElementById('title').textContent='Grounding review — '+(D.label||D.run_id);
document.getElementById('sub').textContent=[D.ts,D.model,'run '+D.run_id,'budgets '+B.join(' / '),
  'budget order '+D.order.map(o=>o.join('→')).join(', ')].join(' · ');

function highlight(pre,text,phrases){
  const low=text.toLowerCase().replace(/\s+/g,' ');
  // Work on a whitespace-collapsed copy so a phrase split across the
  // extractor's line breaks still matches, as it does in the answer key.
  const flat=text.replace(/\s+/g,' ');
  let spans=[];
  (phrases||[]).forEach(p=>{const q=p.toLowerCase().replace(/\s+/g,' ');let i=low.indexOf(q);
    while(i>=0){spans.push([i,i+q.length]);i=low.indexOf(q,i+1)}});
  spans.sort((a,b)=>a[0]-b[0]);
  let pos=0;
  spans.forEach(([a,b])=>{if(a<pos)return;pre.appendChild(document.createTextNode(flat.slice(pos,a)));
    pre.appendChild(el('mark',null,flat.slice(a,b)));pos=b});
  pre.appendChild(document.createTextNode(flat.slice(pos)));
}

function verdict(id,field,label){
  const row=el('div','vrow');row.appendChild(el('span','lab',label));
  [['y','Yes'],['p','Partly'],['n','No']].forEach(([v,t])=>{
    const lab=el('label');const inp=el('input');inp.type='radio';inp.name=id+'|'+field;inp.value=v;
    if((S[id]||{})[field]===v)inp.checked=true;
    inp.addEventListener('change',()=>{S[id]=Object.assign(S[id]||{},{[field]:v});save();refresh()});
    lab.appendChild(inp);lab.appendChild(el('span',null,t));row.appendChild(lab)});
  return row;
}

function arm(item,b){
  const a=item.arms[b];const box=el('div','arm');
  box.appendChild(el('div','bud',b+' chars'));
  if(!a){box.appendChild(el('div','empty','not run at this budget'));return box}
  const chips=el('div','chips');
  const c=(t,k)=>{chips.appendChild(el('span','chip'+(k?' '+k:''),t))};
  c('TTFT '+(a.ttft/1000).toFixed(2)+'s');
  if(a.ptok!=='')c(a.ptok+' tok');
  c(a.passages+' of '+a.sources+' passage'+(a.sources===1?'':'s')+' read', a.passages<a.sources?'warn':'');
  if(a.in_ctx===true)c('book answer in excerpt','ok');
  else if(a.in_ctx===false)c(!a.rank?'book answer not retrieved':(a.rank<=a.passages?
    'book answer shortened out of #'+a.rank:'book answer ranked #'+a.rank+', not read'),'bad');
  if(a.overlap!=null)c('overlap '+Math.round(a.overlap*100)+'%', a.overlap<0.25?'bad':(a.overlap<0.5?'warn':'ok'));
  if(a.drift!=='' && a.drift!=null)c(a.drift+' pages from topic', a.drift>D.drift_pages?'bad':'');
  box.appendChild(chips);
  box.appendChild(el('div','ans',a.answer||'(empty reply)'));
  const det=el('details');
  det.appendChild(el('summary',null,a.context?('What the model read — '+a.context.length+' chars'):
    (a.context===''?'No excerpts — answered from the model alone':'Excerpts not returned by this backend')));
  if(a.context){const pre=el('pre');highlight(pre,a.context,item.key);det.appendChild(pre)}
  box.appendChild(det);
  const id=item.id+'|'+b;
  box.appendChild(verdict(id,'g','Grounded'));
  box.appendChild(verdict(id,'c','Correct'));
  const note=el('input','note');note.placeholder='note (optional)';note.value=(S[id]||{}).note||'';
  note.addEventListener('input',()=>{S[id]=Object.assign(S[id]||{},{note:note.value});save()});
  box.appendChild(note);
  return box;
}

function render(){
  const f=document.getElementById('filter').value,sh=document.getElementById('show').value;
  const host=document.getElementById('items');host.textContent='';
  D.items.forEach(item=>{
    if(f!=='all'&&item.set!==f)return;
    if(sh==='todo'&&B.every(b=>!item.arms[b]||((S[item.id+'|'+b]||{}).g&&(S[item.id+'|'+b]||{}).c)))return;
    const card=el('div','item');const h=el('div','ihead');
    h.appendChild(el('span','tag','Set '+item.set));
    if(item.followup)h.appendChild(el('span','tag fu','pronoun follow-up'));
    h.appendChild(el('span','tag',item.chapter));
    h.appendChild(el('div','q',item.question));
    if(item.after)h.appendChild(el('div','after','asked after: “'+item.after+'”'));
    if(item.key&&item.key.length){const k=el('div','key');k.appendChild(document.createTextNode('Book says: '));
      item.key.forEach((p,i)=>{if(i)k.appendChild(document.createTextNode(' or '));k.appendChild(el('span',null,p))});
      h.appendChild(k)}
    card.appendChild(h);
    const arms=el('div','arms');arms.style.setProperty('--n',B.length);
    B.forEach(b=>arms.appendChild(arm(item,b)));card.appendChild(arms);host.appendChild(card);
  });
}

function refresh(){
  let done=0,total=0;
  const tally={};
  D.items.forEach(item=>B.forEach(b=>{if(!item.arms[b])return;total++;
    const s=S[item.id+'|'+b]||{};if(s.g&&s.c)done++;
    const k=item.set+'|'+b;tally[k]=tally[k]||{g:{y:0,p:0,n:0},c:{y:0,p:0,n:0}};
    if(s.g)tally[k].g[s.g]++;if(s.c)tally[k].c[s.c]++}));
  document.getElementById('prog').textContent=done+' of '+total+' answers scored';
  const t=document.getElementById('summary');t.textContent='';
  const hr=el('tr');['Set','Budget','Turns','Median TTFT','Median prompt tok','Two passages read',
    'Book answer in excerpt','Median overlap','Grounded Y / P / N','Correct Y / P / N']
    .forEach(x=>hr.appendChild(el('th',null,x)));t.appendChild(hr);
  D.summary.forEach(r=>{const tr=el('tr');const k=tally[r.set+'|'+r.budget]||{g:{y:0,p:0,n:0},c:{y:0,p:0,n:0}};
    [r.set==='A'?'A · standalone':'B · follow-ups',r.budget,r.turns,r.ttft,r.ptok,r.both,r.in_ctx,r.overlap,
     k.g.y+' / '+k.g.p+' / '+k.g.n,k.c.y+' / '+k.c.p+' / '+k.c.n].forEach(x=>tr.appendChild(el('td',null,String(x))));
    t.appendChild(tr)});
}

document.getElementById('filter').addEventListener('change',render);
document.getElementById('show').addEventListener('change',render);
document.getElementById('clear').addEventListener('click',()=>{if(confirm('Clear every score on this page?')){S={};save();render();refresh()}});
document.getElementById('export').addEventListener('click',()=>{
  const q=v=>'"'+String(v==null?'':v).replace(/"/g,'""')+'"';
  const rows=[['run_id','set','budget','question','is_followup','turn_id','ttft_ms','passages_read',
    'book_answer_in_excerpt','overlap','grounded','correct','note']];
  const word={y:'yes',p:'partly',n:'no'};
  D.items.forEach(item=>B.forEach(b=>{const a=item.arms[b];if(!a)return;const s=S[item.id+'|'+b]||{};
    rows.push([D.run_id,item.set,b,item.question,item.followup?1:0,a.turn_id,a.ttft,a.passages,
      a.in_ctx==null?'':(a.in_ctx?1:0),a.overlap==null?'':a.overlap,word[s.g]||'',word[s.c]||'',s.note||''])}));
  const csv='﻿'+rows.map(r=>r.map(q).join(',')).join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='grounding-scores-'+D.run_id+'.csv';
  document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
});

const g=document.getElementById('gate');
g.appendChild(el('div','q','Retrieval gate check — “'+D.gate.question+'”'));
g.appendChild(el('div','after',D.gate.sources===0?'PASS: retrieved nothing, as it should. The reply below came from the model alone — judge whether it should have answered at all.':
  'FAIL: retrieved '+D.gate.sources+' passages for an off-syllabus question.'));
g.appendChild(el('div','ans',D.gate.answer||'(empty reply)'));
render();refresh();
})();
</script></body></html>
"""


def _median_or_dash(vals, fmt):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return fmt(statistics.median(vals)) if vals else "-"


def write_eval_html(log_dir, run_id, label, model, base, rows, budgets, order):
    """The grading sheet: every answer at every budget, beside what it read.

    Built from the first pass only. Grading is the slow part -- a person reads
    each answer against its excerpt -- and a second pass of the same question at
    the same budget adds reading, not information about the budget. Timings in
    the summary table still use every pass.
    """
    try:
        items, index = [], {}
        for r in rows:
            if r["pass_no"] != 1:
                continue
            ident = f"{r['set_name']}-{r['thread_no']}-{r['turn_in_thread']}"
            if ident not in index:
                index[ident] = len(items)
                items.append({
                    "id": ident, "set": r["set_name"], "question": r["question"],
                    "chapter": r["expected_chapter"], "followup": bool(r["is_followup"]),
                    "after": r.get("_after") or "", "key": ANSWER_KEY.get(r["question"], []),
                    "arms": {},
                })
            items[index[ident]]["arms"][str(r["budget"])] = {
                "ttft": r["ttft_ms"], "ptok": r["prompt_tokens"],
                "sources": r["sources"], "passages": r["passages_read"],
                "in_ctx": r.get("_in_ctx"), "rank": r["answer_rank"] or None,
                "overlap": r["excerpt_overlap"] if r["excerpt_overlap"] != "" else None,
                "drift": r["drift_pages"], "answer": r["answer"],
                "context": r.get("_context"), "turn_id": r["turn_id"],
            }
        summary = []
        for s in ("A", "B"):
            for b in budgets:
                rs = [r for r in rows if r["set_name"] == s and r["budget"] == b]
                if not rs:
                    continue
                grounded = [r for r in rs if r["sources"]]
                keyed = [r for r in rs if r.get("_in_ctx") is not None]
                summary.append({
                    "set": s, "budget": b, "turns": len(rs),
                    "ttft": _median_or_dash([r["ttft_ms"] for r in grounded],
                                            lambda v: f"{v / 1000:.2f}s"),
                    "ptok": _median_or_dash([r["prompt_tokens"] for r in grounded],
                                            lambda v: f"{v:.0f}"),
                    "both": (f"{sum(1 for r in grounded if r['passages_read'] >= 2)}"
                             f"/{len(grounded)}"),
                    "in_ctx": (f"{sum(1 for r in keyed if r['_in_ctx'])}/{len(keyed)}"
                               if keyed else "-"),
                    "overlap": _median_or_dash(
                        [r["excerpt_overlap"] for r in grounded],
                        lambda v: f"{v * 100:.0f}%"),
                })
        gate = next((r for r in rows if r["pass_no"] == 0), None)
        data = {
            "run_id": run_id, "label": label, "model": model, "base": base,
            "ts": rows[0]["ts_utc"] if rows else "", "budgets": [str(b) for b in budgets],
            "order": [[str(b) for b in o] for o in order], "drift_pages": DRIFT_PAGES,
            "items": items, "summary": summary,
            "gate": {"question": ABSTAIN_CHECK,
                     "sources": gate["sources"] if gate else 0,
                     "answer": gate["answer"] if gate else ""},
        }
        # "</" would end the <script> block early if an answer ever contained it.
        blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        log_dir.mkdir(parents=True, exist_ok=True)
        stem = f"grounding-review-{label}-{run_id}" if label else f"grounding-review-{run_id}"
        path = log_dir / f"{stem}.html"
        path.write_text(_EVAL_PAGE.replace("__DATA__", blob), encoding="utf-8")
        return path
    except OSError as exc:
        print(f"\n  could not write the grading sheet: {exc}")
        return None


def get(base, path):
    with urllib.request.urlopen(f"{base}{path}", timeout=10) as r:
        return json.load(r)


def ask(base, question, session_id=None, budget=None):
    """One streamed turn, optionally continuing an existing conversation.

    Returns client-side timings, the turn_id from the start frame, the top
    citation from the sources frame, and Ollama's own counters from the done
    frame. That last pair is what splits a slow turn into prefill and
    generation -- the two need different fixes, and ttft cannot tell them apart.

    Passing session_id is what makes this measure a conversation rather than a
    series of first questions, which is the only way a pronoun follow-up means
    anything at all.
    """
    # POST /api/chat/stream reads session_id off the JSON body (ChatRequest);
    # only the EventSource GET variant takes it as a query parameter.
    request_body = {"message": question}
    if session_id:
        request_body["session_id"] = session_id
    if budget:
        # Per request, so every arm shares one warm model and one prompt cache;
        # a restart per budget would change more than the budget.
        request_body["context_max_chars"] = budget
    # Always ask for the excerpt text the model read. It is the only thing an
    # answer can be graded against: the citations list every retrieved passage,
    # including ones the budget cut before the prompt.
    request_body["return_context"] = True
    body = json.dumps(request_body).encode()
    req = urllib.request.Request(
        f"{base}/api/chat/stream",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    start = time.perf_counter()
    out = {"ttft_ms": None, "answer": "", "answer_chars": 0, "sources": 0,
           "turn_id": "", "session_id": "", "model": "", "usage": {},
           "top_page": "", "top_heading": "", "top_distance": "", "citations": [],
           "context": None}
    parts = []
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            if kind == "start":
                out["turn_id"] = event.get("turn_id") or ""
                out["session_id"] = event.get("session_id") or ""
                out["model"] = event.get("model") or ""
            elif kind == "sources":
                srcs = event.get("sources") or []
                out["sources"] = len(srcs)
                # Every citation, not just the best one: verifying an answer
                # against the book means opening each page it claims to rest on.
                out["citations"] = srcs
                # None when the backend predates return_context -- the report
                # then says so rather than grading against nothing.
                if "context" in event:
                    out["context"] = event.get("context") or ""
                if srcs:
                    # Best-ranked hit: retrieval returns them ordered, and it is
                    # the one that dominates the prompt.
                    top = srcs[0]
                    out["top_page"] = top.get("page_start", "")
                    out["top_heading"] = (top.get("heading") or "").strip()[:40]
                    out["top_distance"] = top.get("distance", "")
            elif kind == "token":
                if out["ttft_ms"] is None:
                    out["ttft_ms"] = int((time.perf_counter() - start) * 1000)
                parts.append(event.get("content") or "")
            elif kind == "done":
                # Ollama's own counters. Without them a slow turn cannot be split
                # into prefill and generation, which need opposite fixes -- this
                # branch was lost once in a rewrite and every usage column came
                # back empty, so it is worth the comment.
                out["usage"] = event.get("usage") or {}
            elif kind == "error":
                print(f"    stream error: {event.get('detail')}")
                break
    out["total_ms"] = int((time.perf_counter() - start) * 1000)
    out["answer"] = "".join(parts).strip()
    out["answer_chars"] = len(out["answer"])
    return out


def source_label(row):
    """'p.108 Light 0.31' -- where the answer came from, and how sure."""
    if not row["sources"]:
        return "-"
    dist = row["top_distance"]
    dist = f" {dist:.2f}" if isinstance(dist, (int, float)) else ""
    head = row["top_heading"][:16]
    return f"p.{row['top_page']}{' ' + head if head else ''}{dist}"


def summarise_answer_key(scored):
    """Print how often the answer passage reached the model, topics and
    follow-ups apart, and name every miss. `scored` is (is_followup, question,
    score) triples."""
    keyed = [(f, q, s) for f, q, s in scored if s.get("keyed")]
    if not keyed:
        return
    print("\nanswer passage reached the prompt")
    for label, want in (("topic questions", False), ("pronoun follow-ups", True)):
        group = [(q, s) for f, q, s in keyed if f == want]
        if not group:
            continue
        read = sum(1 for _, s in group if s.get("answer_in_prompt"))
        unknown = sum(1 for _, s in group if s.get("answer_in_prompt") is None)
        tail = f"  ({unknown} unknown -- backend predates in_prompt)" if unknown else ""
        print(f"  {label:22} {read}/{len(group)}{tail}")
    follow_scores = [s for f, _, s in keyed if f]
    if follow_scores:
        states = {s.get("query_carried") for s in follow_scores}
        if states == {None}:
            note = "unknown -- backend predates query_carried"
        else:
            note = (f"{sum(1 for s in follow_scores if s.get('query_carried'))}"
                    f"/{len(follow_scores)} searched with their topic question")
        print(f"  {'follow-ups carried':22} {note}")
    misses = [(q, s) for _, q, s in keyed if not s.get("answer_in_prompt")]
    for q, s in misses:
        print(f"  {answer_label(s):>8}   \"{q}\"")
    if misses:
        print("  #n = rank of the answer passage; 'cut' = ranked in the top 2 but")
        print("  dropped by the character budget; 'missed' = not retrieved at all.")


def run_retrieval_only(base, threads, no_followups):
    """The answer key without generation: every question through the library
    search, scored, in seconds. For iterating on retrieval -- chunking, the
    gate, carrying -- without waiting on the model for every change."""
    print(f"\n{'question':52} {'answer':>9}  {'carried':>7}")
    print("-" * 72)
    scored = []
    for topic, followup, _chapter in threads:
        asks = [(False, topic, None)]
        if not no_followups:
            asks.append((True, followup, topic))
        for is_followup, question, previous in asks:
            score = score_retrieval(base, question, previous_question=previous)
            scored.append((is_followup, question, score))
            carried = {True: "yes", False: "no", None: "?"}[score.get("query_carried")]
            shown = ("  L " if is_followup else "") + question
            print(f"{shown[:52]:52} {answer_label(score):>9}  {carried:>7}")
    print("-" * 72)
    summarise_answer_key(scored)
    # Unkeyed on purpose: the only thing to check is that nothing came back.
    req = urllib.request.Request(
        f"{base}/api/library/search",
        data=json.dumps({"question": ABSTAIN_CHECK, "k": ANSWER_SEARCH_K}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            n = len(json.load(resp).get("hits") or [])
        print(f"\nretrieval gate        {'PASS' if n == 0 else 'FAIL'} - "
              f"\"{ABSTAIN_CHECK}\" retrieved {n} passages")
    except Exception as exc:                       # noqa: BLE001
        print(f"\nretrieval gate        could not check: {exc}")
    print()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Latency and grounding benchmark for a packaged AI Tutor.",
    )
    parser.add_argument("base", nargs="?", default=DEFAULT_BASE,
                        help=f"backend URL (default {DEFAULT_BASE})")
    parser.add_argument("--label", default="",
                        help="tag for this run, e.g. exp006 -- carried into benchmarks.csv")
    parser.add_argument("--budgets", default=",".join(str(b) for b in DEFAULT_BUDGETS),
                        help="context budgets to sweep, comma-separated "
                             f"(default {','.join(str(b) for b in DEFAULT_BUDGETS)})")
    parser.add_argument("--set", choices=("A", "B", "both"), default="both",
                        help="A = standalone questions, B = topic + pronoun follow-up "
                             "threads (default both)")
    parser.add_argument("--repeat", type=int, default=1,
                        help="passes over everything; the budget order rotates each "
                             "pass so no budget always runs on the warmest machine")
    parser.add_argument("--topics", type=int, default=0, metavar="N",
                        help="only the first N questions of each set, for a quick look")
    parser.add_argument("--no-followups", action="store_true",
                        help="set B topic questions only; skips the drift test")
    parser.add_argument("--log-dir", default="",
                        help="where the output files go (default: the backend's log directory)")
    parser.add_argument("--no-log", action="store_true",
                        help="print only; write no files")
    parser.add_argument("--retrieval-only", action="store_true",
                        help="score the answer key through the library search and stop; "
                             "no generation, so it takes seconds")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    threads = THREADS[: args.topics] if args.topics > 0 else THREADS
    standalone = STANDALONE[: args.topics] if args.topics > 0 else STANDALONE
    run_a, run_b = args.set in ("A", "both"), args.set in ("B", "both")

    try:
        budgets = [int(b) for b in args.budgets.split(",") if b.strip()]
    except ValueError:
        print(f"--budgets takes whole numbers, e.g. 1200,1000,800 -- got {args.budgets!r}")
        return 2
    out_of_range = [b for b in budgets if not 200 <= b <= 4000]
    if not budgets or out_of_range:
        print(f"--budgets must each be between 200 and 4000 -- got {args.budgets!r}")
        return 2

    try:
        health = get(base, "/health")
    except Exception as exc:                       # noqa: BLE001
        print(f"Backend not reachable at {base}: {exc}")
        print("Start the AI Tutor first, then re-run.")
        return 1

    lib = health.get("library") or {}
    model_name = (health.get("model") or {}).get("name") or ""
    print(f"\nbackend   {base}   status={health.get('status')}")
    print(f"model     {model_name}   "
          f"ollama={'up' if (health.get('ollama') or {}).get('reachable') else 'DOWN'}")
    print(f"library   available={lib.get('available')}  "
          f"docs={lib.get('documents')}  chunks={lib.get('chunks')}  "
          f"model={lib.get('embedding_model')}")
    if args.retrieval_only:
        return run_retrieval_only(base, threads, args.no_followups)

    run_id = uuid.uuid4().hex[:12]
    print(f"run       {run_id}" + (f"   label={args.label}" if args.label else ""))
    per_budget = ((len(standalone) if run_a else 0)
                  + (len(threads) * (1 if args.no_followups else 2) if run_b else 0))
    turns = per_budget * len(budgets) * args.repeat
    # ~9s a turn on the target: ~4-6s to first token, the rest generating.
    print(f"plan      set {'A+B' if run_a and run_b else args.set} x budgets "
          f"{'/'.join(str(b) for b in budgets)} x {args.repeat} pass(es) = "
          f"{turns} turns, about {max(1, round(turns * 9 / 60))} min on the target")

    # The first turn pays any remaining model load, which is not what a student
    # sees on their second question -- excluded from everything.
    print("\nwarming up (first turn absorbs the cold start)...")
    ask(base, "Hello")

    rows, order = [], []

    def make_row(set_name, budget, pass_no, thread_no, turn_in_thread, question,
                 chapter, r, score, drift, after):
        context = r["context"]
        in_ctx = answer_in_context(question, context)
        if in_ctx is not None:
            # Budget-correct. score_retrieval judged this against the SITE budget,
            # which is wrong for every other arm; the text the model read is not.
            score["answer_in_prompt"] = in_ctx
            # The answer's passage was read, just not the part holding the
            # answer: shortening lost it, not the budget.
            rank = score.get("answer_rank")
            score["answer_shortened"] = (
                in_ctx is False and isinstance(rank, int)
                and rank <= passages_in(context))
        overlap = excerpt_overlap(r["answer"], context)
        usage = r["usage"]
        total_ms = r["total_ms"]
        return {
            "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_id": run_id, "label": args.label,
            "set_name": set_name, "budget": budget,
            "pass_no": pass_no, "thread_no": thread_no,
            "turn_in_thread": turn_in_thread, "is_followup": int(turn_in_thread == 2),
            "question": question, "expected_chapter": chapter,
            "turn_id": r["turn_id"], "session_id": r["session_id"],
            "ttft_ms": r["ttft_ms"] or 0, "total_ms": total_ms,
            "answer_chars": r["answer_chars"],
            "chars_per_second": round(r["answer_chars"] / (total_ms / 1000), 1) if total_ms else "",
            "sources": r["sources"], "top_page": r["top_page"],
            "top_heading": r["top_heading"], "top_distance": r["top_distance"],
            "source_pages": ",".join(str(c.get("page_start", "")) for c in r["citations"]),
            "drift_pages": drift,
            "query_carried": {True: 1, False: 0}.get(score["query_carried"], ""),
            "answer_rank": score["answer_rank"] or "",
            "answer_in_prompt": {True: 1, False: 0}.get(score["answer_in_prompt"], ""),
            "context_chars": len(context) if context is not None else "",
            "passages_read": passages_in(context) if context is not None else "",
            "excerpt_overlap": overlap if overlap is not None else "",
            "prompt_tokens": usage.get("prompt_tokens", ""),
            "prefill_ms": usage.get("prompt_eval_ms", ""),
            "completion_tokens": usage.get("completion_tokens", ""),
            "generation_ms": usage.get("eval_ms", ""),
            "tokens_per_second": usage.get("tokens_per_second", ""),
            "load_ms": usage.get("load_duration_ms", ""),
            "model": r["model"] or model_name, "base_url": base,
            "answer": r["answer"], "context": context or "",
            # Carried for the transcript and grading sheet; not CSV columns.
            "_citations": r["citations"], "_score": score, "_context": context,
            "_in_ctx": in_ctx, "_after": after,
        }

    def show(row):
        shown = ("  L " if row["turn_in_thread"] == 2 else "") + row["question"]
        in_ctx = {True: "yes", False: "NO", None: "-"}[row["_in_ctx"]]
        ov = row["excerpt_overlap"]
        ov = f"{ov * 100:.0f}%" if isinstance(ov, float) else "-"
        drift = row["drift_pages"]
        drift = (f"{drift}p" + ("!" if drift > DRIFT_PAGES else "")) if isinstance(drift, int) else ""
        print(f"{shown[:46]:46} {row['ttft_ms'] / 1000:6.2f}s "
              f"{str(row['prompt_tokens'] or '-'):>5} "
              f"{str(row['passages_read']):>2}/{row['sources']:<2} "
              f"{in_ctx:>6} {ov:>7} {drift:>6}")

    header = (f"{'question':46} {'ttft':>7} {'ptok':>5} {'read':>5} "
              f"{'answer':>6} {'overlap':>7} {'drift':>6}")

    for pass_no in range(1, args.repeat + 1):
        # Rotated, so across passes each budget runs early and late. Within a
        # pass the order is budget-major: two runs of the same question at
        # different budgets are always separated by every other question, so
        # neither can inherit the other's cached prompt prefix. A smaller budget
        # run straight after a larger one on the same question shares its whole
        # leading excerpt, and looks far faster than it is.
        k = (pass_no - 1) % len(budgets)
        this_order = budgets[k:] + budgets[:k]
        order.append(this_order)
        for budget in this_order:
            print(f"\n[pass {pass_no} . budget {budget} chars]")
            print(header)
            print("-" * len(header))
            if run_a:
                for qno, (question, chapter) in enumerate(standalone, start=1):
                    r = ask(base, question, budget=budget)
                    # After the turn, never before it, so the extra search cannot
                    # touch the timing being measured.
                    score = score_retrieval(base, question)
                    row = make_row("A", budget, pass_no, qno, 1, question, chapter,
                                   r, score, "", "")
                    rows.append(row)
                    show(row)
            if run_b:
                for tno, (topic, followup, chapter) in enumerate(threads, start=1):
                    # One session per topic per budget: the follow-up needs its
                    # topic question in history, and nothing else.
                    sid, root_page = None, None
                    asks = [(1, topic)] if args.no_followups else [(1, topic), (2, followup)]
                    for turn_in_thread, question in asks:
                        r = ask(base, question, session_id=sid, budget=budget)
                        sid = r["session_id"]
                        score = score_retrieval(
                            base, question,
                            previous_question=topic if turn_in_thread == 2 else None)
                        drift = ""
                        if turn_in_thread == 1:
                            root_page = r["top_page"] if r["sources"] else None
                        elif root_page not in (None, "") and r["sources"]:
                            try:
                                drift = abs(int(r["top_page"]) - int(root_page))
                            except (TypeError, ValueError):
                                drift = ""
                        row = make_row("B", budget, pass_no, tno, turn_in_thread,
                                       question, chapter, r, score, drift,
                                       topic if turn_in_thread == 2 else "")
                        rows.append(row)
                        show(row)

    if not rows:
        print("\nNothing ran -- check --set and --topics.\n")
        return 1
    if all(r["_context"] is None for r in rows):
        print("\n  NOTE: this backend does not return the excerpt text (return_context),")
        print("  so 'answer', 'read' and 'overlap' could not be measured. Update the app")
        print("  layer -- the budget itself was still applied if the backend accepts it.")

    # --- the sweep, summarised ---------------------------------------------
    def med(rs, key):
        vals = [r[key] for r in rs if isinstance(r[key], (int, float))]
        return statistics.median(vals) if vals else None

    print(f"\n{'':18} {'budget':>6} {'ttft':>7} {'ptok':>5} {'2 read':>7} "
          f"{'answer':>7} {'overlap':>7}")
    print("-" * 64)
    for s, label in (("A", "A standalone"), ("B", "B follow-ups")):
        for b in budgets:
            rs = [r for r in rows if r["set_name"] == s and r["budget"] == b and r["sources"]]
            if not rs:
                continue
            keyed = [r for r in rs if r["_in_ctx"] is not None]
            t, p, o = med(rs, "ttft_ms"), med(rs, "prompt_tokens"), med(rs, "excerpt_overlap")
            both = sum(1 for r in rs if isinstance(r["passages_read"], int) and r["passages_read"] >= 2)
            print(f"{label:18} {b:>6} "
                  f"{(f'{t / 1000:.2f}s' if t is not None else '-'):>7} "
                  f"{(f'{p:.0f}' if p is not None else '-'):>5} "
                  f"{f'{both}/{len(rs)}':>7} "
                  f"{(f'{sum(1 for r in keyed if r["_in_ctx"])}/{len(keyed)}' if keyed else '-'):>7} "
                  f"{(f'{o * 100:.0f}%' if o is not None else '-'):>7}")
    print("  2 read = both passages reached the prompt; answer = the book's answer")
    print("  phrase is in the text the model read. Medians over grounded turns only.")

    # What each budget cost, by name: book answers retrieved in the top two
    # that the model still never read -- either the budget dropped their
    # passage, or the passage was read but shortened to a part without them.
    first = budgets[0]
    for b in budgets:
        cut = [r for r in rows if r["budget"] == b and r["_in_ctx"] is False
               and r["answer_rank"] in (1, 2)]
        print(f"\nbook answer retrieved but not read at {b}: "
              + ("none" if not cut else f"{len(cut)}"))
        for r in cut:
            why = "shortened out" if r["_score"].get("answer_shortened") else "budget"
            print(f"  {r['set_name']}  \"{r['question']}\"  ({why})")

    # Retrieval does not depend on the budget -- only the trimming after it does
    # -- so drift is the same at every budget. Reported once.
    if run_b and not args.no_followups:
        fs = [r for r in rows if r["is_followup"] and r["budget"] == first and r["pass_no"] == 1]
        drifted = [r for r in fs if isinstance(r["drift_pages"], int) and r["drift_pages"] > DRIFT_PAGES]
        print(f"\nfollow-up grounding   {len(fs) - len(drifted)}/{len(fs)} stayed within "
              f"{DRIFT_PAGES} pages of their topic question (budget-independent)")
        for r in drifted:
            print(f"  DRIFT {r['drift_pages']:>3} pages   \"{r['question']}\"   "
                  f"expected {r['expected_chapter']}, got p.{r['top_page']} {r['top_heading']}")

    print(f"\nanswer key at {first} chars, as the site runs it by default:")
    summarise_answer_key([(bool(r["is_followup"]), r["question"], r["_score"])
                          for r in rows if r["budget"] == first and r["pass_no"] == 1])

    # This checks the RETRIEVAL GATE, and only that. On 11 Sep it passed -- no
    # passages -- while the reply said France won the 2022 final. The gate did
    # its job and the model answered anyway, from its own (wrong) knowledge. A
    # pass here therefore means "no textbook page was misused", not "the tutor
    # behaved"; the reply is printed so a person can judge the second part.
    check = ask(base, ABSTAIN_CHECK)
    ok = check["sources"] == 0
    print(f"\nretrieval gate        {'PASS' if ok else 'FAIL'} - "
          f"\"{ABSTAIN_CHECK}\" retrieved {check['sources']} sources"
          f"{'' if ok else ' (expected 0; the distance gate let it through)'}")
    print(f"  tutor replied: {check['answer'][:110]}"
          f"{'...' if len(check['answer']) > 110 else ''}")
    print("  (the gate only proves no page was misused -- read the reply to judge the answer)")
    gate_score = {"answer_rank": None, "answer_in_prompt": None, "query_carried": None,
                  "keyed": False}
    gate_row = make_row("-", "", 0, 0, 0, ABSTAIN_CHECK, "(none expected)",
                        check, gate_score, "", "")
    rows.append(gate_row)

    if not args.no_log:
        log_dir = resolve_log_dir(args.log_dir)
        path = append_rows(log_dir, rows)
        if path:
            print(f"\nappended {len(rows)} rows to {path}")
        transcript = write_transcript(log_dir, run_id, args.label, model_name, base, rows)
        if transcript:
            print(f"answers   {transcript}")
        sheet = write_eval_html(log_dir, run_id, args.label, model_name, base,
                                rows, budgets, order)
        if sheet:
            print(f"grading   {sheet}")
            print("          open in Chrome or Edge: every answer at every budget, beside the")
            print("          exact excerpt it read, with Grounded / Correct to mark and export.")

    print("\nttft is what a student waits for, and prefill is most of it -- 18.2ms per")
    print("prompt token here, measured. Each budget step trades roughly half a second")
    print("per 100 characters against the chance that the second passage -- sometimes")
    print("the one holding the answer -- never reaches the model.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
