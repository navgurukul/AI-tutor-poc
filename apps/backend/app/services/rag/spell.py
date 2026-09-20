"""A second, repaired search for a Hindi/Marathi question that looks misheard.

Why this exists. On 2026-09-18 a live question reached retrieval as
"जैब संसाधन क्या होता है" -- ब for व, the classic Devanagari speech-to-text slip
-- and retrieved the *renewable* resources passage instead of the *biotic*
(जैव) one. The model then explained the wrong concept fluently. Searched with
the correct spelling the right passage ranked first, so the corpus, the
chunker and the gate were all fine: a one-letter error in the query was enough
to send a confident wrong hit past the gate.

What it does. Every word of the question that the library has NEVER seen is
looked up under confusable letters. The letters speech recognition (and hasty
typing) routinely swaps -- व/ब, श/ष/स, ण/न, short/long vowel signs,
chandrabindu/anusvara, nukta -- are collapsed to one form, so जैब and जैव are
the same key. If the library has a spelling for it, that becomes a VARIANT of
the question: the same words with the library's own spelling. A dictionary
lookup, no model.

A variant is a candidate, never a rewrite. Retrieval always searches the
question as it was spoken and searches the variant IN ADDITION, pooling both
sets of candidates (see `retrieve`). A wrong guess therefore costs a few extra
candidates, not the right answer -- which is what makes it safe to guess at
all, and is why nothing here ever replaces what the student said.

What it deliberately does NOT do: fix a dropped, extra or wrong letter
(संसधन for संसाधन). That was built and measured on 2026-09-18 and removed. An
unknown word is not the same thing as a misspelt one -- it is usually a real
word the library happens not to use -- and with nothing but the library's own
words to judge by, "one edit away" cannot tell the two apart. Holding out 15%
of the corpus and correcting the real words that only occurred there, the
one-edit tier rewrote 12% of them, often into a different word (पूजा -> पूरा,
शादी -> सारी, सूखने -> सीखने): a correct question turned into a confident wrong
search, which is the very failure this module exists to prevent. Confusable
letters alone rewrote 0.6%, every one a harmless spelling variant (ज़्यादा ->
ज्यादा, हिरन -> हिरण), while still recovering 100% of synthetic ब/व-style slips.

Why it is safe to be this narrow:

  - Only unknown words are touched. A word the library contains is never
    "corrected", however rare, so a real term cannot be rewritten into a
    commoner one.
  - It adds a search; it never removes one. The student's own words are
    always searched too, and neither the student nor the model ever sees the
    variant -- the answer is still to the question that was asked.
  - It costs a second search only for a question that contains a word the
    library has never seen AND has a confusable spelling in it. Any other
    question pays nothing.
  - Latin-script words pass through untouched. English speech goes through the
    browser's recogniser, which does not make this class of error.
  - It costs the request nothing it can feel: the vocabulary is built in a
    background thread, and until it is ready the question is simply searched
    as-is. Nothing here ever waits on it, and nothing here calls a model.
"""

import logging
import re
import threading
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# A run of Devanagari letters and signs. Stops before the danda (U+0964/5),
# digits (U+0966-F) and the abbreviation sign, which are punctuation to a
# spelling check, not part of a word. ZWNJ/ZWJ (U+200C/D) sit inside words
# that need a visible half-form; they are kept in the match and dropped from
# the key so a word spelled with and without one is the same word.
_WORD = re.compile("[ऀ-ॣॱ-ॿ‌‍]+")

# Letters collapsed for MATCHING only; the correction returned is always a
# real spelling taken from the library, never this reduced form.
_CONFUSABLE = str.maketrans(
    {
        "व": "ब",  # the one that started this
        "श": "स",
        "ष": "स",
        "ण": "न",
        "ी": "ि",  # long/short vowel signs
        "ू": "ु",
        "ई": "इ",  # ... and their independent forms
        "ऊ": "उ",
        "ँ": "ं",  # chandrabindu / anusvara
        "़": None,  # nukta: ड़ vs ड, ज़ vs ज
        "‌": None,
        "‍": None,
    }
)

# Shorter than this a word is almost always a particle the library certainly
# contains, and too short for a confusable match to mean anything.
_MIN_WORD = 3
# A candidate spelling must be an established word, not a stray OCR fragment.
_MIN_FREQ = 2
# A question that needs more repairs than this is more likely out of scope
# (or spoken in another register) than mistyped.
_MAX_FIXES = 3


def _norm(word: str) -> str:
    """NFC, with joiners removed. NFC also splits the precomposed nukta letters
    (U+0958-F) into base + nukta, so the corpus and the question agree."""
    return unicodedata.normalize("NFC", word).replace("‌", "").replace("‍", "")


def _canon(word: str) -> str:
    return word.translate(_CONFUSABLE)


@dataclass(frozen=True)
class Correction:
    original: str
    corrected: str


class Vocabulary:
    """Every Devanagari word in the library, with how often it occurs."""

    __slots__ = ("freq", "canon_index")

    def __init__(self, freq: Counter):
        self.freq: Dict[str, int] = dict(freq)
        # confusable-letter form -> (most common real spelling, count of the class)
        best: Dict[str, Tuple[int, str]] = {}
        totals: Dict[str, int] = defaultdict(int)
        for word, count in self.freq.items():
            key = _canon(word)
            if not key:
                continue
            totals[key] += count
            if key not in best or count > best[key][0]:
                best[key] = (count, word)
        self.canon_index: Dict[str, Tuple[str, int]] = {
            key: (best[key][1], totals[key]) for key in totals
        }

    def __len__(self) -> int:
        return len(self.freq)


def build_vocabulary(texts: Iterable[str]) -> Vocabulary:
    counts: Counter = Counter()
    for text in texts:
        for match in _WORD.finditer(text):
            word = _norm(match.group())
            if len(word) >= 2:
                counts[word] += 1
    return Vocabulary(counts)


def _best_candidate(word: str, vocab: Vocabulary) -> Optional[str]:
    """The library's own spelling of this word under confusable letters."""
    hit = vocab.canon_index.get(_canon(word))
    if hit is not None and hit[1] >= _MIN_FREQ:
        return hit[0]
    return None


def variant(question: str, vocab: Vocabulary) -> Tuple[Optional[str], List[Correction]]:
    """The question with its unknown words respelled, or None if nothing changed."""
    fixes: List[Correction] = []
    pieces: List[str] = []
    cursor = 0
    for match in _WORD.finditer(question):
        word = _norm(match.group())
        if len(fixes) >= _MAX_FIXES or len(word) < _MIN_WORD or word in vocab.freq:
            continue
        fixed = _best_candidate(word, vocab)
        if fixed is None or fixed == word:
            continue
        pieces.append(question[cursor:match.start()])
        pieces.append(fixed)
        cursor = match.end()
        fixes.append(Correction(match.group(), fixed))
    if not fixes:
        return None, []
    pieces.append(question[cursor:])
    return "".join(pieces), fixes


# -- the shared vocabulary ---------------------------------------------------
# One for the whole library, not one per grade: a correction only fixes a
# spelling, and retrieval is scoped to the student's grade afterwards anyway.
_lock = threading.Lock()
_vocab: Optional[Vocabulary] = None
_building = False
# Bumped whenever the corpus changes, so a build that started before an upload
# or a delete cannot publish a vocabulary of a library that no longer exists.
_generation = 0


def invalidate() -> None:
    """Drop the vocabulary; the next question starts a rebuild. Call after the
    corpus changes."""
    global _vocab, _generation
    with _lock:
        _generation += 1
        _vocab = None


def ensure_built(store) -> None:
    """Start a background build if there is no vocabulary and none in flight.

    Never blocks and never raises: a question asked while this runs is just
    searched as spoken, which is what happened before this module existed.
    """
    global _building
    with _lock:
        if _vocab is not None or _building:
            return
        _building = True
        generation = _generation
    threading.Thread(
        target=_build, args=(store, generation), daemon=True, name="spell-vocabulary"
    ).start()


def _build(store, generation: int) -> None:
    global _vocab, _building
    vocab: Optional[Vocabulary] = None
    try:
        vocab = build_vocabulary(store.iter_chunk_texts())
        logger.info("Spelling vocabulary ready: %d distinct words.", len(vocab))
    except Exception:  # noqa: BLE001 - a background job must never die silently
        logger.exception("Could not build the spelling vocabulary")
    finally:
        with _lock:
            _building = False
            if vocab is not None and generation == _generation:
                _vocab = vocab


def query_variant(question: str, store) -> Tuple[Optional[str], List[Correction]]:
    """An extra question worth searching alongside the original, or None."""
    vocab = _vocab
    if vocab is None:
        ensure_built(store)
        return None, []
    return variant(question, vocab)
