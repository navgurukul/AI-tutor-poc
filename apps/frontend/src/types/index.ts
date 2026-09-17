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
