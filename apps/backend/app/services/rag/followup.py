"""Questions that cannot be searched for on their own.

"How can we reduce it?" is a perfectly clear question to a student who just
asked about friction, and meaningless to an embedding model. The topic is not
in the sentence -- it is in the previous turn -- so the vector lands wherever
the leftover words point. In exp004 on the target (Class 6 Science, 11 Sep)
that question retrieved soil erosion (p.17) and the balanced-diet pyramid
(p.64) at 0.33-0.36, inside the 0.42 gate, and the tutor answered from them.
Six of the ten pronoun follow-ups in that run left their chapter the same way.
The distances look healthy because a question with no content is a mediocre
match for everything, so no threshold can catch it.

The fix is to put the topic back before embedding, by carrying the previous
question along: "What is frictional force? How can we reduce it?" retrieves
the friction section at 0.21. Replayed against the shipped index, carrying put
the answer passage first for seven of those ten follow-ups, against four.

Carrying it on EVERY turn is not the fix, and measuring that is what shaped
this module (on the multilingual branch, commit a47bee3). "What is
photosynthesis?" asked after a chemistry question retrieves nothing at all on
its own -- correctly, the corpus does not cover it, and the tutor says so.
Carried, it retrieved ATOMIC NUMBER, cleared the gate, and answered a botany
question out of the chemistry chapter. Always-on trades one silent failure for
another.

So it is conditional, and the condition is the thing that actually causes the
problem: a reference pointing outside the sentence. A question that changes
topic does not contain one -- nobody writes "what is photosynthesis?" with a
dangling "it" -- which is exactly why this test separates the two cases when a
distance threshold cannot.

The same goes for a question that leaves the topic out instead of pointing at
it: "Why?", "Give me an example.", "Tell me more." Nothing in them names a topic,
so nothing in them can change it. Searched and answered on their own, "Why?"
after a lever question got skin and clothing threads, and "Tell me more." after
a shadow question explained the book's "Can you recall?" box. Since 17 Sep this test also decides whether
the MODEL sees the previous question at all (Session.history), so a miss here
loses the conversation, not just the search.
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
    # Hindi / Marathi, which have the same problem and the same fix. Kept on
    # this English-only branch so the module stays identical to the
    # multilingual one: a student can still type Devanagari here.
    "यह", "वह", "ये", "वे", "इस", "उस", "इन", "उन",
    "इसे", "उसे", "इसका", "उसका", "इसकी", "उसकी", "इसके", "उसके",
    "इसमें", "उसमें", "इनका", "उनका", "इनमें", "उनमें",
    "त्याचा", "त्याची", "त्यात", "याचा", "याची", "यात", "ते", "तो", "ती",
}

# Words that ask without naming anything. A question made of nothing else
# ("Why?", "Can you give me another example?") has left its topic in the last
# turn. English only: the Devanagari equivalents are untested.
_ASKING = {
    "why", "how", "what", "when", "where", "which", "who",
    "is", "are", "was", "were", "do", "does", "did",
    "can", "could", "will", "would", "should",
    "i", "me", "you", "we", "us", "please",
    "give", "tell", "explain", "show", "describe", "say", "mean",
    "a", "an", "the", "some", "any", "another", "other", "one",
    "more", "again", "else", "example", "examples", "detail", "details",
    "simply", "simpler", "further", "about", "so", "and", "then", "really",
}

_WORD = re.compile(r"[\wऀ-ॿ]+", re.UNICODE)


def is_context_dependent(question: str) -> bool:
    """True when the question leans on something it does not name.

    A word test rather than a length or distance test on purpose. Shortness is
    not the problem -- "What is a lever?" is short and searches perfectly well
    -- and the distance cannot be the trigger either, because the whole hazard
    is that a contentless question produces distances that look healthy.
    """
    words = [w.lower() for w in _WORD.findall(question or "")]
    if not words:
        return False
    return any(w in _DANGLING for w in words) or all(w in _ASKING for w in words)


def embedding_text(question: str, previous_question: Optional[str]) -> str:
    """What to actually embed for this question.

    The previous QUESTION, not the previous answer: the answer is the model's
    own prose, several times longer, and averaging it into the vector drowns
    the thing being asked about. One turn back, not the whole conversation, for
    the same reason.
    """
    if not previous_question or not is_context_dependent(question):
        return question
    # No question text in the log: these run on classroom laptops, and the
    # turn logs already keep what a child asked out of every file.
    logger.debug("Carrying the previous question into retrieval.")
    return "{} {}".format(previous_question.strip(), question.strip())
