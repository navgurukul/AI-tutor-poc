import type { AskTutorRequest, AskTutorResponse, Citation } from "../types";
import { mockAnswerFor } from "./mockData";

const API_BASE_URL =
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
}

/** Body shared by /api/chat and /api/chat/stream. */
function chatBody(payload: AskTutorRequest) {
  return {
    message: payload.message,
    session_id: payload.sessionId,
    profile: payload.profile && {
      subject: payload.profile.subject,
      level: payload.profile.level,
      style: payload.profile.style,
      language: payload.profile.language,
      student_name: payload.profile.studentName,
    },
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
  return { sessionId: data.session_id, answer: data.reply };
}

export interface WarmupResult {
  model: string;
  /** Ollama's reported model-load time; ~0 when it was already resident. */
  loadDurationMs: number;
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
  profile?: { subject?: string; level?: string },
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
        profile: profile && { subject: profile.subject, level: profile.level },
      }),
      signal,
    });
    if (!res.ok) return null;
    const data = (await res.json()) as {
      model: string;
      usage?: { load_duration_ms?: number };
    };
    return { model: data.model, loadDurationMs: data.usage?.load_duration_ms ?? 0 };
  } catch {
    return null;
  }
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
  /** Fired once the model is finished, with the server's trimmed reply. */
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
            handlers.onDone?.({ sessionId, answer: reply });
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
