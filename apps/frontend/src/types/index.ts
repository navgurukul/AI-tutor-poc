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
}

/**
 * How retrieval behaved on one question. Mirrors the backend `RetrievalMetrics`.
 *
 * Reference-free: none of it measures correctness, because there is no golden
 * answer at question time. `scripts/evaluate_retrieval.py` against the golden
 * set is still the only thing that measures recall. These are the proxies that
 * move with it, shown per turn so a regression is visible before anyone reruns
 * the harness.
 */
export interface RetrievalMetrics {
  query_language: string;
  /** The distance ceiling that applied — it is per query language. */
  ceiling: number;
  grade?: number | null;
  lexical_query: boolean;

  embed_ms: number;
  dense_ms: number;
  lexical_ms: number;
  total_ms: number;

  candidates: number;
  dense_hits: number;
  gate_survivors: number;
  lexical_hits: number;
  lexical_eligible: number;
  fused: number;
  returned: number;
  dropped_over_budget: number;

  best_distance?: number | null;
  /** ceiling - best_distance. Near zero means the answer only just cleared. */
  headroom?: number | null;
  /** Gap from the best dense hit to the runner-up. */
  separation?: number | null;
  both_legs: number;

  context_tokens: number;
  context_budget: number;

  abstained: boolean;
  abstain_reason: string;
}

/** What one answer cost, end to end. Mirrors the backend `TurnMetrics`. */
export interface TurnMetrics {
  retrieval: RetrievalMetrics;

  retrieval_ms: number;
  /** Server-side time to first token; null on the buffered endpoint. */
  ttft_ms?: number | null;
  llm_ms: number;
  retry_ms: number;
  total_ms: number;

  load_ms: number;
  prefill_ms: number;
  decode_ms: number;
  overhead_ms: number;

  prompt_tokens: number;
  completion_tokens: number;
  tokens_per_second: number;

  groundedness?: number | null;
  /** Why `groundedness` is null. Empty when a score is present. */
  groundedness_note?: string;
}

/**
 * The server's numbers plus the two the browser is the only one that can see.
 *
 * The server's clock starts when the request arrives. For a spoken question
 * the student has already waited through capture and transcription by then,
 * and after the last token they wait again for speech — so a turn that looks
 * fast on the server can still feel slow in the room. Both are kept, and the
 * gap between them is where the speech pipeline lives.
 */
export interface ClientTurnMetrics extends TurnMetrics {
  /** Question submitted → first token rendered. */
  client_ttft_ms?: number;
  /** Question submitted → last token rendered. */
  client_total_ms?: number;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  /** Present on tutor replies that retrieval found textbook passages for. */
  sources?: Citation[];
  /** Present once the reply has finished streaming. */
  metrics?: ClientTurnMetrics;
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
  /** Absent if the backend predates the metrics contract, or on a mock reply. */
  metrics?: TurnMetrics;
}
