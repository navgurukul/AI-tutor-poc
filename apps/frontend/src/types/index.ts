export interface SchoolClass {
  id: string;
  name: string;
}

export interface Subject {
  id: string;
  name: string;
}

export type ChatRole = "user" | "tutor";

/**
 * A textbook passage the tutor's answer was grounded in.
 *
 * Mirrors the backend `Source` model, so the field names stay snake_case.
 */
export interface Citation {
  title: string;
  heading?: string;
  page_start: number;
  page_end: number;
  grade?: number | null;
  subject?: string | null;
  /** Cosine distance; smaller is a closer match. Kept for debugging. */
  distance?: number;
  /**
   * The passage as it went into the prompt, shortened to the question. Null
   * when the character budget cut it: the page was retrieved and is cited, but
   * the model never read it.
   */
  excerpt?: string | null;
}

/**
 * What one reply cost, measured in the browser.
 *
 * Shown next to the citations because the two answer the same question from
 * opposite sides: the citations say where the answer came from, these say what
 * it took to get. On a CPU-only laptop that is the difference between a tutor
 * that feels alive and one a student gives up on, and it is worth being able to
 * read on the device itself rather than only in a benchmark.
 */
export interface TurnMetrics {
  /** Time to the first token -- what the student actually waits through. */
  ttftMs: number;
  /** Time to the complete reply. */
  totalMs: number;
  /** Reply length, so a slow turn can be told from a merely long one. */
  chars: number;
}

/**
 * How much of a reply the textbook excerpt it read actually supports.
 *
 * Only computed for questions from the groundedness gold set
 * (docs/groundedness/evalset.json), graded claim by claim after the reply
 * finishes. Mirrors the backend's response, so the field names stay snake_case.
 */
export interface Groundedness {
  item: string;
  /** Supported claims / scored claims; null when the reply made no claims. */
  groundedness: number | null;
  claims: number;
  supported: number;
  unsupported: number;
  contradicted: number;
  /** Questions and invitations to the student, which assert nothing. */
  not_scored: number;
  judge: string;
  judge_kind: "llm" | "lexical";
  /** Set when the configured judge could not be used. */
  note?: string;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  /** Present on tutor replies that retrieval found textbook passages for. */
  sources?: Citation[];
  /** Present once a tutor reply has finished streaming. */
  metrics?: TurnMetrics;
  /** Gold-set questions only: "pending" while the judge runs. */
  groundedness?: Groundedness | "pending" | "failed";
  /** Joins the reply to its record in /api/eval/turns/{turnId}. */
  turnId?: string;
}

export type TeachingStyle = "socratic" | "direct" | "exam_prep";

export interface TutorProfile {
  subject?: string;
  level?: string;
  style?: TeachingStyle;
  language?: string;
  studentName?: string;
}

export interface AskTutorRequest {
  message: string;
  sessionId?: string;
  profile?: TutorProfile;
}

export interface AskTutorResponse {
  sessionId: string;
  answer: string;
  /** The question is in the gold set and the reply is waiting to be graded. */
  groundednessPending?: boolean;
}

/** One retrieved passage in a turn record (backend services/turndetail.py). */
export interface RetrievedChunk {
  rank: number;
  chunk_id: number;
  title: string;
  heading: string;
  page_start: number;
  page_end: number;
  grade: number | null;
  subject: string | null;
  /** Cosine distance; smaller is closer. Null when the dense search did not return it. */
  distance: number | null;
  /** Fused RRF score (AFE retrieval only); higher is better. */
  score?: number;
  /** Which searches found it: dense, lexical, section (AFE retrieval only). */
  matched_via?: string[];
  chars_retrieved: number;
  chars_sent: number;
  /** False = retrieved, but the character budget cut it before the prompt. */
  sent: boolean;
  /** The text as it went into the prompt; null when not sent. */
  excerpt: string | null;
}

/**
 * Everything about one turn: retrieval, the prompt sent, Ollama's timings and
 * the answer. Mirrors the backend record, so field names stay snake_case.
 */
export interface TurnDetail {
  ts_utc: string;
  turn_id: string;
  session_id: string;
  question: string;
  previous_question: string | null;
  followup: boolean;
  retrieval: {
    ms: number;
    query: string;
    mode?: "afe" | "legacy";
    /** "800 tokens" (AFE) or "1000 chars" (legacy). */
    budget: string;
    top_k: number;
    context_chars: number;
    chunks: RetrievedChunk[];
  };
  prompt: {
    model: string;
    options: Record<string, number>;
    messages: Array<{ role: string; content: string }>;
    prompt_chars: number;
  };
  llm: {
    prompt_tokens: number;
    completion_tokens: number;
    prefill_ms: number;
    decode_ms: number;
    load_ms: number;
    tokens_per_second: number;
    /** From the start of the turn, so it includes retrieval. */
    ttft_ms: number;
    ttft_after_retrieval_ms: number;
    total_ms: number;
  };
  answer: string;
  answer_chars: number;
}

/** A question from docs/groundedness/afe-golden.json. */
export interface GoldenQuestion {
  id: string;
  type: "short" | "mid-size" | "long" | "follow-up";
  class_: number;
  subject: string;
  chapter: string;
  question: string;
  answerShouldMention: string;
  /** One entry per fact; each lists accepted substrings, any one matches. */
  points: string[][];
  followUpOf?: string;
}
