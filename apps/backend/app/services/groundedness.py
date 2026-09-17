"""Claim-level groundedness: does a reply say only what the excerpt it read says?

The scoring core of scripts/eval/groundedness_eval.py, which imports it from
here -- so the number shown under an answer in the UI is the number the harness
would have printed for the same reply, not a look-alike. The method, the judge
design and its measured error rates are in docs/groundedness/README.md.

Only questions in the gold set (docs/groundedness/evalset.json) are graded
live. That is where the judge has been calibrated and where the known-error
patterns exist; anywhere else a percentage would look just as precise and mean
much less. A build that does not ship the gold set simply never grades.

Standard library only, and app.config is imported where it is used: the eval
harness imports this file under a bare python3 with no backend dependencies.
"""

import json
import logging
import re
import urllib.error
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED, UNSUPPORTED, CONTRADICTED = "supported", "unsupported", "contradicted"

# apps/backend/app/services -> repo root.
DEFAULT_EVALSET = Path(__file__).resolve().parents[4] / "docs" / "groundedness" / "evalset.json"


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------
def norm(text):
    """Lower-case, straight quotes, whitespace collapsed -- how every string
    comparison in here is made. The PDF extractor breaks lines mid-sentence, so
    a raw `in` test against the stored text fails on line breaks alone."""
    text = (text or "").replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return " ".join(text.split()).lower()


SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Openers that make a sentence an instruction to the student rather than a
# statement about the world. The style rule requires one at the end of every
# socratic reply, so these are frequent and must not be scored as claims.
_INVITES = re.compile(
    r"^(?:so\s+|now\s+|next\s+time\b|and\s+)?"
    r"(?:try|look|watch|notice|observe|think|consider|imagine|see\s+if|check|"
    r"tell\s+me|can\s+you|could\s+you|do\s+you|have\s+you|what\s+do\s+you|"
    r"why\s+do\s+you|how\s+would\s+you|let's|let\s+us|remember\s+to|"
    r"take\s+a\s+look|ask\s+yourself|note\s+down|write\s+down|draw\b)",
    re.IGNORECASE,
)
# A heading the model emitted despite being told not to ("Key points:").
_HEADING = re.compile(r"^\s*(?:[-*•]\s*)?[A-Z][A-Za-z ]{0,28}:\s*$")


def claims_of(reply):
    """The reply split into (text, kind) -- kind is 'claim' or why it is not.

    Sentence-level, deliberately. Splitting further into atomic propositions
    needs a model, and a model that splits is a model that can drop half a
    sentence before anything has been judged.
    """
    out = []
    for raw in SENTENCE_END.split(" ".join((reply or "").split())):
        s = raw.strip()
        if len(s) < 12:
            continue
        if _HEADING.match(s):
            out.append((s, "heading"))
        elif s.endswith("?"):
            out.append((s, "question"))
        elif _INVITES.match(s):
            out.append((s, "invitation"))
        else:
            out.append((s, "claim"))
    return out


_STOP = set(
    """a about above after again against all also am an and any are as at be because
    been before being below between both but by can could did do does doing down
    during each few for from further had has have having he her here hers him his
    how i if in into is it its itself just like made make many may me more most
    much must my no nor not now of off on once one only or other our out over own
    same she should so some such than that the their them then there these they
    this those through to too under until up upon us very was we were what when
    where which while who whom why will with would you your example examples
    called""".split()
)


def content_words(text):
    words = "".join(c if c.isalpha() else " " for c in norm(text)).split()
    return {w for w in words if len(w) >= 4 and w not in _STOP}


# ---------------------------------------------------------------------------
# the judge
# ---------------------------------------------------------------------------
# Two binary questions, not one three-way verdict, and this is measured rather
# than assumed. Asked for supported/unsupported/contradicted in one shot,
# gemma3:4b wrote the right paraphrase of the excerpt and then chose the wrong
# label: on the calibration set it scored 12/14 but missed real support 17% of
# the time, and a variant that leaned harder on polarity pushed that to 33%.
# Split into "does the excerpt state it?" and then "does the excerpt make it
# false?", the same model scores 11/14 with real support missed 0% of the time
# -- and its remaining errors land on the harmless side, calling a polarity flip
# unsupported rather than waving it through as supported. A claim only costs a
# second call when the first says no.
SUPPORT_SYSTEM = (
    "You are checking a school textbook. Answer only from the EXCERPT.\n"
    "quote: copy word for word the sentence of the excerpt that bears on the "
    "statement, or leave empty.\n"
    "answer yes only if the excerpt states the statement, or the statement "
    "follows directly from what the excerpt states.\n"
    "answer no if the excerpt does not state it, even if you believe it is true."
)
CONTRADICT_SYSTEM = (
    "You are checking a school textbook. Answer only from the EXCERPT.\n"
    "quote: copy word for word the sentence of the excerpt that bears on the "
    "statement, or leave empty.\n"
    "answer yes only if the excerpt says something that makes the statement "
    "FALSE -- the excerpt asserts the reverse, or pairs the things the other way "
    "round (like/unlike, attract/repel, more/less, with/without, before/after, "
    "does/does not).\n"
    "answer no if the excerpt simply does not mention it, or if it agrees with "
    "the statement."
)
# The quote is decoded before the answer, on purpose: the model has to point at
# a line of the excerpt before it is allowed to answer, which is what stops a
# fluent-sounding claim being waved through on the strength of its wording.
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        # Bounded, because an unbounded string field is where a small model
        # goes to loop. Judging the sound excerpt, gemma3:4b got 3,115 tokens
        # into copying it back and was still going when the call was killed ten
        # minutes later -- schema-constrained decoding constrains the shape,
        # not the length. A supporting sentence is never this long.
        "quote": {"type": "string", "maxLength": 300},
        "answer": {"type": "string", "enum": ["yes", "no"]},
    },
    "required": ["quote", "answer"],
}


class JudgeUnavailable(RuntimeError):
    """The judge model could not be reached or is not pulled."""


class LlmJudge:
    name_kind = "llm"

    def __init__(self, model="gemma3:4b", host="http://127.0.0.1:11434",
                 timeouts=(180, 300, 600)):
        self.model, self.host = model, host.rstrip("/")
        # Retried with growing timeouts, because the tutor model, the embedding
        # model and the judge are all resident at once on this hardware and a
        # judge call behind a model swap can sit past any single timeout.
        self.timeouts = timeouts
        self.calls = 0

    def __str__(self):
        return "{} (local, via Ollama)".format(self.model)

    def _ask(self, system, claim, context):
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": "EXCERPT:\n{}\n\nSTATEMENT: {}".format(
                    context.strip(), claim.strip())},
            ],
            "stream": False,
            "format": JUDGE_SCHEMA,
            # num_predict is the belt to maxLength's braces: the quote cap
            # stops the loop inside the string, this stops one anywhere else.
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 300},
            "keep_alive": "10m",
        }
        req = urllib.request.Request(
            self.host + "/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        last = None
        for timeout in self.timeouts:
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    out = json.load(resp)
                break
            except urllib.error.HTTPError as exc:
                # A 404 is a model that is not pulled; waiting will not fix it.
                raise JudgeUnavailable("{} answered {}".format(self.model, exc.code))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                logger.info("judge call timed out (%ss), retrying", timeout)
        else:
            raise JudgeUnavailable(
                "the judge stopped responding after {} attempts ({})".format(
                    len(self.timeouts), last))
        self.calls += 1
        content = (out.get("message") or {}).get("content") or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Truncated at num_predict. Say so rather than silently scoring it
            # "no" -- a quietly wrong verdict is worse than a visible gap.
            logger.warning("judge returned unparseable JSON (%s chars); treating "
                           "as no answer", len(content))
            parsed = {}
        return (str(parsed.get("answer", "")).strip().lower() == "yes",
                (parsed.get("quote") or "").strip())

    def verdict(self, claim, context):
        if not (context or "").strip():
            return UNSUPPORTED, ""
        supported, quote = self._ask(SUPPORT_SYSTEM, claim, context)
        if supported:
            return SUPPORTED, quote
        contradicted, quote = self._ask(CONTRADICT_SYSTEM, claim, context)
        return (CONTRADICTED if contradicted else UNSUPPORTED), quote


class LexicalJudge:
    """No model: a claim counts as supported when the excerpt covers most of its
    content words. Cannot see polarity -- "like poles attract" scores exactly as
    well as "like poles repel" -- so it can never report a contradiction. Here
    for a machine with no judge model, and labelled as triage wherever shown."""

    name_kind = "lexical"
    THRESHOLD = 0.6

    def __init__(self):
        self.calls = 0

    def __str__(self):
        return "word overlap >= {:.0%} (no model; blind to polarity)".format(self.THRESHOLD)

    def verdict(self, claim, context):
        self.calls += 1
        said = content_words(claim)
        if not said or not (context or "").strip():
            return UNSUPPORTED, ""
        share = len(said & content_words(context)) / len(said)
        return (SUPPORTED if share >= self.THRESHOLD else UNSUPPORTED,
                "overlap {:.2f}".format(share))


# ---------------------------------------------------------------------------
# grading one reply
# ---------------------------------------------------------------------------
def quote_is_real(quote, hay_context):
    """Is the line the judge said it was reading actually in the excerpt?

    The judge is told to copy a sentence word for word, so this is checkable,
    and it is worth checking: over the first full run it echoed the claim back
    as its own evidence once, and recalled a sentence of the book that was not
    in the excerpt once -- 2 of 28 supported verdicts resting on a line that was
    never in front of it.

    It flags, it does not overrule. The verdict can be right while the quote is
    sloppy, so a rule that downgraded on this would trade a judge error for a
    harness error. Sentence by sentence, because the judge often returns two
    excerpt sentences joined, and joining them changes neither.
    """
    if not quote:
        return None
    parts = [norm(p) for p in SENTENCE_END.split(quote)]
    parts = [p for p in parts if len(p) >= 20]
    if not parts:
        return None
    return all(p in hay_context for p in parts)


def grade_claims(reply, context, judge, known_errors=()):
    """Every sentence of the reply, graded against the excerpt: (graded, skipped).

    Known errors override the judge, in that direction only. Each pattern was
    written against the book by hand for one question ("like poles attract", "a
    lever has two parts"), so a match is a contradiction whatever the judge
    thought.
    """
    hay_context = norm(context)
    graded, skipped = [], []
    for text, kind in claims_of(reply):
        if kind != "claim":
            skipped.append({"text": text, "kind": kind})
            continue
        hit = next((f for f in known_errors if re.search(f["pattern"], norm(text))), None)
        if hit:
            graded.append({"text": text, "verdict": CONTRADICTED,
                           "evidence": "known error: " + hit["why"], "by": "pattern",
                           "quote_found": True})
            continue
        verdict, evidence = judge.verdict(text, context)
        graded.append({"text": text, "verdict": verdict, "evidence": evidence,
                       "by": judge.name_kind,
                       "quote_found": quote_is_real(evidence, hay_context)})
    return graded, skipped


# ---------------------------------------------------------------------------
# live grading of gold-set questions
# ---------------------------------------------------------------------------
_evalset: Optional[Dict[str, Any]] = None


def _key(question: Optional[str]) -> str:
    """Spoken questions arrive without a question mark and in any case."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).split())


def _load_evalset() -> Dict[str, Any]:
    from app.config import settings

    global _evalset
    if _evalset is None:
        path = Path(settings.groundedness_evalset or DEFAULT_EVALSET)
        try:
            _evalset = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.info("No gold set at %s, live groundedness off: %s", path, exc)
            _evalset = {"items": []}
    return _evalset


def match_item(question: str, previous_question: Optional[str]) -> Optional[Dict[str, Any]]:
    """The gold item this turn is, or None.

    A follow-up item only matches down the session it was written for: "How can
    we reduce it?" after a question about friction is that item, and after one
    about soil erosion it is a different question with the same words.
    Off-syllabus items are scored on citations, not claims, so they never match.
    """
    from app.config import settings

    if not settings.groundedness_live:
        return None
    wanted = _key(question)
    for item in _load_evalset().get("items") or []:
        if item.get("must_abstain") or _key(item.get("query")) != wanted:
            continue
        if item.get("previous_question") and (
            _key(item["previous_question"]) != _key(previous_question)
        ):
            continue
        return item
    return None


# Turns waiting to be graded, by turn id. The stream ends before grading starts,
# so the student is never kept waiting on a judge; the UI asks afterwards.
_pending: "OrderedDict[str, Tuple[Dict[str, Any], str, str]]" = OrderedDict()
_PENDING_MAX = 32


def remember_turn(turn_id: str, item: Dict[str, Any], reply: str, context: str) -> None:
    _pending[turn_id] = (item, reply, context)
    while len(_pending) > _PENDING_MAX:
        _pending.popitem(last=False)


def grade_turn(turn_id: str) -> Optional[Dict[str, Any]]:
    """Grade a remembered turn. Blocking -- run it off the event loop."""
    from app.config import settings

    entry = _pending.pop(turn_id, None)
    if entry is None:
        return None
    item, reply, context = entry

    judge: Any
    note = ""
    if settings.groundedness_judge.strip().lower() == "lexical":
        judge = LexicalJudge()
    else:
        judge = LlmJudge(settings.groundedness_judge, settings.ollama_host, timeouts=(120,))
    try:
        graded, skipped = grade_claims(reply, context, judge,
                                       item.get("forbidden_claims") or [])
    except JudgeUnavailable as exc:
        # A word-overlap number is worth less than a judged one, but a turn with
        # no number at all is the worse outcome for someone checking the tutor.
        logger.warning("Judge unavailable (%s); falling back to word overlap.", exc)
        note = "{} unavailable".format(settings.groundedness_judge)
        judge = LexicalJudge()
        graded, skipped = grade_claims(reply, context, judge,
                                       item.get("forbidden_claims") or [])

    counts = {v: sum(1 for c in graded if c["verdict"] == v)
              for v in (SUPPORTED, UNSUPPORTED, CONTRADICTED)}
    return {
        "turn_id": turn_id,
        "item": item["id"],
        "groundedness": (round(counts[SUPPORTED] / len(graded), 3) if graded else None),
        "claims": len(graded),
        "supported": counts[SUPPORTED],
        "unsupported": counts[UNSUPPORTED],
        "contradicted": counts[CONTRADICTED],
        "not_scored": len(skipped),
        "judge": str(judge),
        "judge_kind": judge.name_kind,
        "note": note,
        "verdicts": graded,
    }
