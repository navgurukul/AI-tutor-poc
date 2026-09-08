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

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  /** Present on tutor replies that retrieval found textbook passages for. */
  sources?: Citation[];
  /** Present once a tutor reply has finished streaming. */
  metrics?: TurnMetrics;
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
}
