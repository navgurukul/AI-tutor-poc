"""Questions that cannot be searched for on their own.

"What are the particles inside it?" is a perfectly clear question to a person
reading the conversation and meaningless to an embedding model. The topic is
not in the sentence -- it is in the previous turn -- so the vector lands
wherever the leftover words point. Measured on the Class 9 corpus, that
question retrieved *Factors Affecting Evaporation* at distance 0.423: inside
the 0.51 English ceiling, so the gate accepted it, and the tutor answered about
atomic structure out of a page on evaporation with the page number printed
underneath. That is the failure the gate exists to prevent, arriving through
the one door it cannot watch -- the distances look fine, because a question
with no content is a mediocre match for everything.

The fix is to put the topic back before embedding, by carrying the previous
question along: "What is an atom? What are the particles inside it?" retrieves
*4.2 The Structure of an Atom* at 0.326.

Carrying it on EVERY turn is not the fix, and measuring that is what shaped
this module. "What is photosynthesis?" asked after a chemistry question
retrieves nothing at all on its own -- correctly, the corpus does not cover it,
and the tutor says so. Carried, it retrieves ATOMIC NUMBER at 0.421, clears the
ceiling, and answers a botany question out of the chemistry chapter. Always-on
trades one silent failure for another.

So it is conditional, and the condition is the thing that actually causes the
problem: a reference pointing outside the sentence. A question that changes
topic does not contain one -- nobody writes "what is photosynthesis?" with a
dangling "it" -- which is exactly why this test separates the two cases when a
distance threshold cannot.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Words whose meaning lives in an earlier turn. Kept to genuine anaphora:
# every one of these, standing alone in a question, points at something the
# sentence does not name.
_DANGLING = {
    # English
    "it", "its", "they", "them", "their", "theirs",
    "this", "that", "these", "those",
    "he", "him", "his", "she", "her", "hers",
    "one", "ones", "both",
    # Hindi / Marathi, which have the same problem and the same fix. Devanagari
    # retrieval works (bge-m3 was chosen for it), so these questions reach the
    # embedder in the same shape.
    "यह", "वह", "ये", "वे", "इस", "उस", "इन", "उन",
    "इसे", "उसे", "इसका", "उसका", "इसकी", "उसकी", "इसके", "उसके",
    "इसमें", "उसमें", "इनका", "उनका", "इनमें", "उनमें",
    "त्याचा", "त्याची", "त्यात", "याचा", "याची", "यात", "ते", "तो", "ती",
}

_WORD = re.compile(r"[\wऀ-ॿ]+", re.UNICODE)


def is_context_dependent(question: str) -> bool:
    """True when the question leans on something it does not name.

    A word test rather than a length or distance test on purpose. Shortness is
    not the problem -- "What is an atom?" is short and searches perfectly well
    -- and the distance cannot be the trigger either, because the whole hazard
    is that a contentless question produces distances that look healthy.
    """
    if not question:
        return False
    return any(w.lower() in _DANGLING for w in _WORD.findall(question))


def embedding_text(question: str, previous_question: Optional[str]) -> str:
    """What to actually embed for this question.

    The previous QUESTION, not the previous answer: the answer is the model's
    own prose, several times longer, and averaging it into the vector drowns
    the thing being asked about. One turn back, not the whole conversation, for
    the same reason.

    Only the dense leg should use this. The lexical leg keeps the question as
    the student typed it -- BM25 ORs its terms, so folding in the previous
    question's words widens the match rather than focusing it.
    """
    if not previous_question or not is_context_dependent(question):
        return question
    carried = "{} {}".format(previous_question.strip(), question.strip())
    logger.debug("Carrying the previous question into retrieval: %r", carried[:120])
    return carried
