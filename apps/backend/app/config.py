"""Application settings.

Everything is overridable through environment variables or a `.env` file so the
frontend developer can point the backend at a different Ollama host or model
without touching code.
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "AI Tutor POC"
    version: str = "0.1.0"

    # --- Ollama -----------------------------------------------------------
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:1.5b"
    # A 1.5B model on CPU is quick, but a long answer plus a cold model load
    # can still take a while, so the read timeout is generous.
    ollama_timeout_seconds: float = 180.0
    ollama_connect_timeout_seconds: float = 5.0

    # Ollama unloads an idle model after 5 minutes by default, and reloading
    # this one costs ~2s -- a student who pauses between questions would pay it
    # every time. Accepts Ollama's own forms: a number of seconds ("-1" never
    # unloads, "0" unloads immediately) or a duration ("30m", "1h").
    ollama_keep_alive: str = "-1"
    # Load the model at boot so the first question of the session doesn't pay
    # the load cost. Runs in the background; startup never waits on it.
    warm_model_on_startup: bool = True

    # --- Generation defaults ---------------------------------------------
    # 0.3, down from 0.7 (exp006, 11 Sep). At 0.7, 14 of the 24 questions that
    # got byte-identical excerpts at three budgets were right at one and wrong
    # at another -- magnet poles came out inverted, correct, then muddled, off
    # the same text. That is a 1.5B model sampling between readings of its own
    # evidence, and a tutor should give its most likely reading every time.
    # Sampling costs nothing measurable, so this is not a latency setting.
    temperature: float = 0.3
    # Caps the tail of a slow turn. The persona already asks for under 200
    # words (~260 tokens); 800 only ever bought a runaway answer, and on a CPU
    # at ~9 chars/s the difference is minutes.
    max_tokens: int = 400
    # Kept well under the model's 32k window; keeps replies fast on CPU.
    num_ctx: int = 4096

    # --- Conversation memory ---------------------------------------------
    # What the model re-reads of the conversation. NOT what the student sees:
    # the full reply is streamed, stored and returned unchanged. These two were
    # one string until they were measured, and that cost 3.9s a turn.
    #
    # The history window used to be a flat "last N messages", which meant the
    # previous *answer* came back in full. At 851 characters that is ~218
    # tokens, and at 18.2ms per prompt token it bought ~3.9s of prefill on
    # every turn after the first -- so answer length was charged twice, once to
    # generate and again to re-read. Measured on target 2026-09-10: turn 1 at
    # 5.6s to first token, turn 5 at 9.2s, rising monotonically with the length
    # of the preceding answer.
    #
    # What the model reads now is ONE student message (sessions.Session.history):
    #
    #   a question that names its topic   the question alone
    #   a follow-up ("how can we reduce   the last `history_questions` questions
    #   it?", "why?")                     named as background, the follow-up,
    #                                     and the style rule's length spelled
    #                                     out again (tutor.FOLLOW_UP_PROMPT)
    #
    # Which is which is the word test retrieval already used to decide whether to
    # search with the previous question (rag.followup.is_context_dependent).
    #
    # No assistant turn goes back, not even a piece of one. Every chat-turn shape
    # failed on a 1.5B model: two questions in a row got both answered, a fixed
    # "(answered)" turn was copied as the whole reply on 7 of 12 pronoun
    # follow-ups, and the opening sentence of the real answer (17 Sep, briefly)
    # was copied for length, leaving 5 of 6 topic switches at one sentence.
    # Against that last version, same corpus, Mac: one-sentence topic switches
    # 5/6 -> 1/6, follow-ups 17/32 -> 9/32; prompt tokens for a new topic
    # 323 -> 294, for a follow-up 327 -> 338.
    #
    # Budget every token above as prefilled, ~25-30 ms each on the target CPU.
    # Older notes here said the replayed question was free because the prompt
    # extended the last one and Ollama's cache covered it. It mostly was not:
    # the excerpts sit in the system message ahead of the conversation and
    # change between turns, so everything after them is read again -- 16 of 18
    # live follow-ups. On the other two, where the excerpts were reused
    # verbatim, the old shape did extend the last prompt and this one does not.
    #
    # Before 16 Sep the closing sentence of the previous answer (~28 tok) came
    # back too, so a student answering the tutor's own question ("because it
    # would go pale?") did not read as a non-sequitur. It was not earning it:
    # 376 tok / 340 ms against 344 tok / 236 ms without it (Mac, excerpt reused
    # verbatim, min of 3 reps).
    #
    # One question back is enough for a pronoun: the immediate antecedent is
    # what it binds to. Raise this if chained follow-ups ("why does that work?"
    # after "how can we reduce it?") start losing the topic.
    history_questions: int = 1
    session_ttl_minutes: int = 180
    max_sessions: int = 500

    # --- Retrieval (RAG) ---------------------------------------------------
    # Textbook retrieval is additive: if the store can't be opened the tutor
    # still answers from the model alone, so a missing library is a degraded
    # feature rather than a broken app.
    rag_enabled: bool = True
    # Kept beside the backend package so it travels with the app; the whole
    # corpus (text + vectors) is one file that can be built centrally and
    # copied onto a device, which is the only sane option on a 15W laptop.
    rag_db_path: str = "data/library.db"
    rag_embedding_model: str = "nomic-embed-text"
    # Must match the model above. Baked into the vec0 table at creation, so
    # changing either means re-ingesting; the store refuses a silent mismatch.
    rag_embedding_dims: int = 768
    # How many chunks are retrieved and pasted into the prompt. Each one costs
    # prefill time on a CPU-bound model, which is the real latency cost of RAG
    # -- the search itself is under a millisecond.
    # Now 2, measured on the target: dropping the third excerpt took prefill
    # from 6.5s to 3.7s and first token from 6.3s to 4.1s. RAG_TOP_K overrides.
    rag_top_k: int = 2
    # Hard ceiling on retrieved text, applied after ranking. rag_top_k alone
    # does not bound latency: prefill costs ~25-30ms per token on the target
    # laptop, and four chunks measured anywhere from 1,178 to 3,376 characters
    # depending on the question -- 10.7s vs 28.6s to first token for the same
    # k. Budgeting characters makes the wait predictable instead of a lottery
    # on which passages happen to be long. Chunks are dropped from the end, so
    # the best-ranked excerpt is always kept.
    #
    # Measured on the target laptop: base prompt with no excerpts reaches first
    # token in 3.3s; 1,178 characters of excerpt takes 10.7s; 3,376 takes
    # 28.6s. Roughly 20-27ms per token of prefill, linear.
    #
    # Now 800, from 1200 (exp006, 30 questions at 1200/1000/800 on the
    # target). A budget only changes a turn when the top passage is short
    # enough for a second one to fit -- 6 of the 30 at 800 -- and those turns
    # got 1.3-6.3s faster: mean first token 4.72s -> 4.06s. The book's answer
    # reached the model on 19 of 30 at every budget; none of the passages 800
    # dropped held it, and two had caused wrong answers at 1200. The catch is
    # that most turns now carry one passage, so which passage ranks first
    # matters more than it did. RAG_CONTEXT_MAX_CHARS overrides; every 100
    # characters is roughly half a second.
    rag_context_max_chars: int = 800
    # Longest a single passage may be in the prompt. The budget above never
    # trims the top passage, so it cannot bound a turn by itself: every turn
    # still over 6s at 800 in exp006 was one passage of 950-1,200 characters,
    # read whole. A passage over this is cut to the run of sentences that best
    # matches the question (retrieval.shorten_passage), which bounds the worst
    # turn at the budget and leaves a short second passage room to fit. At
    # ~25ms per new token on the target, 1,200 -> 600 characters is ~3s.
    # RAG_PASSAGE_MAX_CHARS=0 turns it off.
    rag_passage_max_chars: int = 600
    # Cosine distance above which a hit is treated as irrelevant. Without it a
    # question the textbooks don't cover still drags in the four least-bad
    # chunks and invites the model to answer from them.
    #
    # Calibrated, not guessed: against a Class 9 Science chapter, questions the
    # text answers scored 0.12-0.34 and off-topic ones ("capital of France",
    # "bake bread") scored 0.50-0.58. 0.42 sits in the gap. Re-measure with
    # POST /api/library/search if you change the embedding model.
    rag_max_distance: float = 0.42
    # A follow-up with a dangling pronoun ("how can we reduce it?") is searched
    # with the previous question in front of it, because on its own it embeds
    # to nothing and retrieval wanders into other chapters -- 6 of 10 follow-ups
    # did in exp004. Questions without one are searched exactly as typed; see
    # app.services.rag.followup for why this is conditional. Only the search
    # changes, never the prompt. RAG_CARRY_FOLLOWUPS=0 turns it off, for an
    # A/B run of the benchmark.
    rag_carry_followups: bool = True
    # Ingest-time corpus filtering (app.services.rag.quality). A textbook's
    # exercises, activity boxes and fill-in-the-blanks are ABOUT the chapter's
    # topic, so they embed next to the definition and compete with it -- and a
    # fill-in-the-blank is the definition with the answer deleted. Measured on
    # the Class 6 book (groundedness run v1, 2026-09-16): "What are the poles of
    # a magnet?" retrieved the p.121 exercise first, and the tutor filled the
    # blanks in backwards and taught the student that opposite poles repel.
    #
    # Only applies at ingest, so changing it means re-ingesting the PDF. Off
    # (RAG_FILTER_CORPUS=0) skips the filter but not the reflow in pdf_text, which
    # is not behind a flag: since 2026-09-17 it keeps sentences whole and drops
    # figure captions, so "off" no longer reproduces the 2026-09-16 index.
    rag_filter_corpus: bool = True
    # Share of a page's paragraphs that must be exercise apparatus, alongside at
    # least one explicit instruction stem, before the whole page is dropped.
    # The stem is what makes 0.40 safe, not a gap in the densities: since reflow
    # keeps a prose paragraph whole (2026-09-17), lesson pages holding an answer
    # reach 0.43 (p.42, p.36, p.86) and exercise pages start at 0.44 -- but none
    # of those lesson pages carries a stem. At this value 16 of 132 pages go,
    # 14.8% of the text, and none of the 69 answer phrases in the two evaluation
    # sets is lost. Re-measure for a new book with
    # scripts/eval/corpus_filter_report.py.
    rag_exercise_page_ratio: float = 0.40
    # Prepend "Class 6 > Science > <heading>" to a chunk before embedding, so a
    # paragraph that has stopped naming its subject still carries the chapter's
    # vocabulary.
    #
    # Now OFF by default, on measurement (2026-09-21). Over the 373 chunks of
    # the shipped MSCERT corpus, the breadcrumb injected vocabulary the prose
    # did not already have into 334 of them -- and in 175 of those (47% of the
    # whole corpus) the heading was junk: a flattened table row ("Yes Yes
    # None"), a credits line ("Assistant Special Officer, English"), half a
    # sentence ("The British scientist Michael"). Only 159 (43%) carried a real
    # topic. It was a coin flip, and on NCERT it is worse, because the headings
    # it picks up are running headers ("SCIENCE64", "/ Beehive").
    #
    # The idea is sound; it was sitting on heading detection that was wrong
    # about half the time. Turn it back on once the library's heading
    # validation is shown to have improved that -- and note that turning it off
    # does NOT stop false headings cutting chunks, which is a separate cost.
    rag_embed_breadcrumb: bool = False
    # Characters per chunk, and the overlap carried between neighbours so a
    # definition split across a boundary survives in at least one of them.
    #
    # Sized against rag_passage_max_chars (600) and rag_context_max_chars (800),
    # not on its own. This was 1200, and 1200 only worked by accident: the old
    # reflow broke a chunk at every false heading, so the median chunk was 491
    # characters. Once reflow kept sections whole (2026-09-17) the median doubled
    # to 1,014 and context recall fell from 51% to 32% -- the gravity, lever and
    # sublimation definitions were retrieved, then trimmed out by the passage
    # limit or cut with the second passage by the budget.
    #
    # Swept on the reflowed Class 6 book. Gold quotes reaching the prompt (of 31)
    # + benchmark.py answers (of 30), and gold quotes split across a chunk
    # boundary, which the groundedness gold set refuses to score:
    #
    #   old corpus  16 + 20 = 36   split 0
    #   1200        10 + 16 = 26   split 0
    #   800         16 + 21 = 37   split 2
    #   700         15 + 20 = 35   split 0   <- here
    #   600         17 + 20 = 37   split 1
    #   500         12 + 19 = 31   split 2
    #
    # 600-800 are indistinguishable at this sample size; which quote a boundary
    # happens to cut is luck of placement, not a trend. 700 is the one of them
    # the gold set can score unchanged, which keeps the end-to-end eval
    # comparable with earlier runs. Below 600, more small chunks compete for
    # rag_top_k's two slots. Re-measure if the passage limit or the budget
    # changes -- the three move together.
    rag_chunk_chars: int = 700
    # Overlap was set to 0 on 2026-09-21 and put back to 105 on 2026-09-22.
    # The first measurement was not wrong, it was incomplete, and the way it was
    # incomplete is worth recording.
    #
    # It rebuilt the corpus at 105 and at 0 and checked the 39 gold ANSWER
    # PHRASES from benchmark.py and the groundedness set. All 39 survived either
    # way, so overlap looked like 33 wasted chunks. But those phrases are short
    # -- a few words each -- and a short phrase rarely straddles a boundary.
    #
    # The groundedness set also carries 31 GOLD QUOTES, which are whole
    # multi-sentence passages, and those do straddle. At overlap 0, A1-shadow
    # breaks in half: "If an opaque object comes in the way of a light source,
    # light does not pass through it." lands in one chunk and "...This dark part
    # is called the 'shadow of the object'." in the next, so the definition is
    # in neither chunk whole. 29 of 31 quotes survive at 0; 30 of 31 at 105.
    #
    # The cost is 10 chunks on this book (313 -> 323, +3%), not the +9.7% the
    # first measurement implied, because the corpus is smaller now that front
    # matter is dropped. A definition the model reads in one piece is worth
    # that. Re-measure against the gold QUOTES, not the phrases, if this moves.
    rag_chunk_overlap_chars: int = 105
    # Chunks embedded per Ollama call during ingestion.
    rag_embed_batch_size: int = 16
    # Upload ceiling for a single PDF.
    rag_max_upload_mb: int = 80

    # --- Latency logging --------------------------------------------------
    # Per-turn CSVs in the log directory, for working out where a slow device
    # is spending its time. Shapes and durations only -- never question or
    # answer text, because these files get copied off classroom laptops.
    turn_log_enabled: bool = True

    # --- Live groundedness ------------------------------------------------
    # A question asked word for word from the gold set gets its reply graded
    # claim by claim, and the score shown under the answer. Graded after the
    # stream ends, in a separate request, so no turn waits on it -- but the
    # judge does share Ollama with the tutor, and loading it can push the tutor
    # out of memory and cost the next turn its prompt cache.
    #
    # Off by default: the packaged build ships neither the gold set nor a judge
    # model. GROUNDEDNESS_LIVE=true turns it on for an evaluation session.
    groundedness_live: bool = False
    # Empty = docs/groundedness/evalset.json in the repo. A packaged build does
    # not ship it, and grading is then simply off.
    groundedness_evalset: str = ""
    # An Ollama model, or "lexical" for word overlap (no model, blind to
    # polarity). An unavailable model falls back to lexical, labelled as such.
    groundedness_judge: str = "gemma3:4b"

    # --- Serving / packaging ---------------------------------------------
    # Loopback by default. A packaged device build must never bind 0.0.0.0:
    # the library upload and delete routes have no auth, so a wildcard bind
    # publishes them to every peer on the school network.
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    # Directory of built frontend assets to serve at "/". Empty disables the
    # mount, which is what a developer running Vite on its own port wants. The
    # packaged launcher points this at the installed web/ directory, making the
    # product same-origin and removing the need for Node at runtime.
    web_dir: str = ""
    # Set by the packaged launcher: turns off the interactive API docs and
    # enables the loopback request guards.
    packaged: bool = False

    # --- CORS -------------------------------------------------------------
    # Comma-separated list. "*" is fine for a local POC.
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> List[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
