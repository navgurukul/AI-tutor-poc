import type {
  AskTutorRequest,
  AskTutorResponse,
  Citation,
  TurnMetrics,
  TutorProfile,
} from "../types";
import { mockAnswerFor } from "./mockData";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API === "true";
const MOCK_DELAY_MS = 400;
// Roughly the ~27 tok/s a 1.5B model decodes at on CPU, so the mock exercises
// the same incremental rendering and speech pacing as the real backend.
const MOCK_TOKEN_DELAY_MS = 35;

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function unreachableError(): Error {
  // fetch() rejects (rather than resolving with a bad status) when there's
  // nothing to connect to at all - e.g. the backend process isn't running.
  // That's unrelated to internet access (this URL is localhost), but the
  // raw "Failed to fetch" TypeError reads like a generic network error, so
  // spell out the actual, actionable cause instead.
  return new Error(
    `Can't reach the tutor backend at ${API_BASE_URL}. Make sure it's running ` +
      `(scripts\\start.ps1, or apps/backend/run.sh) - this doesn't require internet.`,
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw unreachableError();
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(
      `${res.status} ${res.statusText}${body ? `: ${body}` : ""}`,
    );
  }

  return res.json() as Promise<T>;
}

interface ChatApiResponse {
  session_id: string;
  reply: string;
  model: string;
  usage: unknown;
  created_at: string;
  metrics?: TurnMetrics;
}

/**
 * The profile, shaped the way the backend expects it.
 *
 * Deliberately shared by the warm-up and by real turns. The warm-up is only
 * worth anything if it assembles the *same* system prompt the first question
 * will: Ollama reuses the cached prefix and prefill drops from ~31ms/token to
 * ~2ms/token (measured 2026-09-09 — a 16.4s prefill down to 1.2s). Two call
 * sites building this object independently is exactly how they drift, and a
 * drifted warm-up is worse than none: it pays a full prefill to prime a prefix
 * that nothing then matches.
 */
function profileBody(profile?: TutorProfile) {
  return (
    profile && {
      subject: profile.subject,
      level: profile.level,
      style: profile.style,
      language: profile.language,
      student_name: profile.studentName,
    }
  );
}

/** Body shared by /api/chat and /api/chat/stream. */
function chatBody(payload: AskTutorRequest) {
  return {
    message: payload.message,
    session_id: payload.sessionId,
    profile: profileBody(payload.profile),
  };
}

/**
 * POST /api/chat - the whole reply in one response.
 *
 * Kept as the simple integration path; the UI uses `askTutorStream` instead,
 * because waiting for a full local generation before anything happens is the
 * single biggest source of felt latency.
 */
export async function askTutor(
  payload: AskTutorRequest,
): Promise<AskTutorResponse> {
  if (USE_MOCK_API) {
    await delay(MOCK_DELAY_MS);
    return {
      sessionId: payload.sessionId ?? "mock-session",
      answer: mockAnswerFor(payload.message),
    };
  }

  const data = await request<ChatApiResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(chatBody(payload)),
  });
  return {
    sessionId: data.session_id,
    answer: data.reply,
    metrics: data.metrics,
  };
}

export interface WarmupResult {
  model: string;
  /** Ollama's reported model-load time; ~0 when it was already resident. */
  loadDurationMs: number;
  /**
   * Tokens in the warm-up's assembled prompt.
   *
   * Worth logging because warming only pays off if this prompt is a *prefix*
   * of the first real question's prompt — that is what Ollama's KV cache
   * reuses, and it takes prefill from ~31ms/token to ~2ms/token (measured
   * 2026-09-09, a 16.4s prefill down to 1.2s). When the two prompts disagree
   * the warm-up silently primes a prefix nothing matches and the first turn
   * pays full price. That is exactly what happened on 2026-09-09: the warm-up
   * assembled 526 tokens and the first question 487, and turn 1 was 14x slower
   * than turn 2. Printing both makes that visible instead of invisible.
   */
  promptTokens: number;
  /**
   * Textbook sections in the warmed prompt.
   *
   * Zero is a real answer, not a failure: the corpus is filtered by grade, so
   * picking a class with no book on the device legitimately warms a prompt with
   * no textbook in it. The lobby surfaces this because it is otherwise
   * invisible — the tutor still answers, just from the model's own knowledge
   * rather than from the book, and nothing on screen would say so.
   */
  passages: number;
  /**
   * The session the warm-up created — the chat page MUST continue it.
   *
   * This is the difference between a first question that takes 1.8s and one
   * that takes 19.5s (measured 2026-09-09). Ollama reuses a cached prefix only
   * when the new prompt *extends* the previous one. A question asked in a fresh
   * session sends [persona + corpus + question], which shares 1356 tokens with
   * the warm-up and then forks — and a fork gets nothing, however long the
   * shared part is. Continuing the session sends
   * [persona + corpus + "warm up" + reply + question], which is a strict
   * continuation, so the whole prefix is reused.
   */
  sessionId: string;
}

/**
 * Warm the tutor model on page load: a throwaway `POST /api/chat` with a 1-token
 * cap and the session profile. It pulls the model into memory (~10s cold-start,
 * weights off disk) and lets Ollama cache the system-prompt prefix, so the
 * student's first real question is fast. No dedicated endpoint — just a normal
 * chat call whose reply is discarded. Fire-and-forget: any failure is swallowed
 * and the first answer is simply as slow as it used to be.
 */
export async function warmupTutor(
  profile?: TutorProfile,
  signal?: AbortSignal,
): Promise<WarmupResult | null> {
  if (USE_MOCK_API) return null;
  try {
    const res = await fetch(`${API_BASE_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "warm up",
        max_tokens: 1,
        // Built by the same helper real turns use, so the system prompt Ollama
        // caches here is byte-identical to the one the first question sends.
        // The backend skips the socratic re-ask for a 1-token reply.
        profile: profileBody(profile),
      }),
      signal,
    });
    if (!res.ok) return null;
    const data = (await res.json()) as {
      model: string;
      session_id?: string;
      usage?: { load_duration_ms?: number };
      metrics?: {
        prompt_tokens?: number;
        retrieval?: { returned?: number };
      };
    };
    return {
      model: data.model,
      loadDurationMs: data.usage?.load_duration_ms ?? 0,
      promptTokens: data.metrics?.prompt_tokens ?? 0,
      passages: data.metrics?.retrieval?.returned ?? 0,
      sessionId: data.session_id ?? "",
    };
  } catch {
    return null;
  }
}

/**
 * Read a DRAFT's likely textbook passage into the backend's cache before the
 * student presses Send -- while they're still speaking or reviewing the box.
 *
 * Fire-and-forget, exactly like `warmupTutor`: the backend answers 202 as
 * soon as it has accepted the request and does the actual work (retrieval,
 * then priming Ollama) in the background, so this never delays anything the
 * student is looking at. A guess that turns out wrong, or arrives too late,
 * costs nothing extra either -- the real Send falls back to today's turn at
 * today's speed. See `RAG_EARLY_PRIME_ENABLED` in the backend for the numbers.
 *
 * Requires a session to attach the guess to (the lobby's warm-up creates one
 * before the student can type or speak anything), so a call with no
 * `sessionId` yet is skipped rather than spending a request on a guess
 * nothing will claim.
 */
export function prepareTutor(
  message: string,
  sessionId: string | undefined,
  profile: TutorProfile | undefined,
  signal?: AbortSignal,
): void {
  if (USE_MOCK_API || !sessionId || !message.trim()) return;
  void fetch(`${API_BASE_URL}/api/chat/prepare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      profile: profileBody(profile),
    }),
    signal,
  }).catch(() => {
    // Best-effort: a failed prepare just means the real question pays the
    // usual cost, same as if this call had never been made.
  });
}

export interface TutorStreamHandlers {
  /** Fired once, before the first token, with the (possibly new) session id. */
  onStart?: (sessionId: string) => void;
  /**
   * Fired once, before the first token, with the textbook passages retrieval
   * put into the prompt. Not fired at all when the library had no match, which
   * is what tells the UI the answer came from the model alone.
   */
  onSources?: (sources: Citation[]) => void;
  /** Fired per token as the model decodes. */
  onToken?: (token: string) => void;
  /**
   * Fired once the model is finished, with the server's trimmed reply and the
   * turn's metrics. The metrics ride on `done` rather than arriving in their
   * own frame because they are read after the answer — and because the
   * retrieval half of them matters most on the turns where `onSources` never
   * fired at all, which is exactly when a sources-shaped frame would be absent.
   */
  onDone?: (result: AskTutorResponse) => void;
}

/** One `data: {...}` frame from the backend's SSE stream. */
interface StreamEvent {
  type: "start" | "sources" | "token" | "done" | "error";
  session_id?: string;
  content?: string;
  reply?: string;
  detail?: string;
  hint?: string;
  sources?: Citation[];
  metrics?: TurnMetrics;
}

async function mockStream(
  payload: AskTutorRequest,
  handlers: TutorStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const sessionId = payload.sessionId ?? "mock-session";
  const answer = mockAnswerFor(payload.message);
  handlers.onStart?.(sessionId);
  await delay(MOCK_DELAY_MS);
  // Split on whitespace but keep it, so the reassembled text matches `answer`.
  for (const token of answer.match(/\S+\s*/g) ?? [answer]) {
    if (signal?.aborted) return;
    handlers.onToken?.(token);
    await delay(MOCK_TOKEN_DELAY_MS);
  }
  handlers.onDone?.({ sessionId, answer });
}

/**
 * POST /api/chat/stream - Server-Sent Events, one `start`, many `token`, one
 * `done`, terminated by `[DONE]`.
 *
 * Tokens are delivered as they are decoded, so the caller can render and speak
 * the first sentence while the rest is still being generated.
 *
 * Errors arrive as an `error` event rather than an HTTP status, because the
 * status is already committed by the time generation begins; they're re-thrown
 * here so callers only have to handle one failure path.
 */
export async function askTutorStream(
  payload: AskTutorRequest,
  handlers: TutorStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  if (USE_MOCK_API) return mockStream(payload, handlers, signal);

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(chatBody(payload)),
      signal,
    });
  } catch (err) {
    // An abort is the caller stopping the turn on purpose, not a failure.
    if ((err as Error)?.name === "AbortError") throw err;
    throw unreachableError();
  }

  if (!res.ok || !res.body) {
    const body = await res.text().catch(() => "");
    throw new Error(
      `${res.status} ${res.statusText}${body ? `: ${body}` : ""}`,
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sessionId = payload.sessionId ?? "";
  let reply = "";
  let metrics: TurnMetrics | undefined;

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line; the trailing fragment is an
      // incomplete frame and stays buffered until the rest of it arrives.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const line = frame
          .split("\n")
          .find((l) => l.startsWith("data:"));
        if (!line) continue;

        const data = line.slice(5).trim();
        if (!data || data === "[DONE]") continue;

        let event: StreamEvent;
        try {
          event = JSON.parse(data) as StreamEvent;
        } catch {
          console.warn("[askTutorStream] skipping malformed frame:", data.slice(0, 200));
          continue;
        }

        switch (event.type) {
          case "start":
            sessionId = event.session_id ?? sessionId;
            handlers.onStart?.(sessionId);
            break;
          case "sources":
            if (event.sources?.length) handlers.onSources?.(event.sources);
            break;
          case "token":
            if (event.content) {
              reply += event.content;
              handlers.onToken?.(event.content);
            }
            break;
          case "done":
            sessionId = event.session_id ?? sessionId;
            reply = event.reply ?? reply;
            metrics = event.metrics ?? metrics;
            handlers.onDone?.({ sessionId, answer: reply, metrics });
            break;
          case "error":
            throw new Error(
              [event.detail ?? "The tutor backend failed mid-answer.", event.hint]
                .filter(Boolean)
                .join(" "),
            );
        }
      }
    }
  } finally {
    // Releasing the lock lets an abort actually tear the connection down, which
    // also stops the model generating server-side.
    reader.cancel().catch(() => undefined);
  }
}
