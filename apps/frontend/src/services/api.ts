import type { AskTutorRequest, AskTutorResponse } from "../types";
import { mockAnswerFor } from "./mockData";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API === "true";
const MOCK_DELAY_MS = 400;

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    // fetch() rejects (rather than resolving with a bad status) when there's
    // nothing to connect to at all - e.g. the backend process isn't running.
    // That's unrelated to internet access (this URL is localhost), but the
    // raw "Failed to fetch" TypeError reads like a generic network error, so
    // spell out the actual, actionable cause instead.
    throw new Error(
      `Can't reach the tutor backend at ${API_BASE_URL}. Make sure it's running ` +
        `(scripts\\start.ps1, or apps/backend/run.sh) - this doesn't require internet.`,
    );
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

/** POST /api/chat { message, session_id?, profile? } -> { session_id, reply, ... } */
export async function askTutor(
  payload: AskTutorRequest,
): Promise<AskTutorResponse> {
  console.log("[askTutor] request payload:", payload);

  let response: AskTutorResponse;
  if (USE_MOCK_API) {
    await delay(MOCK_DELAY_MS);
    response = {
      sessionId: payload.sessionId ?? "mock-session",
      answer: mockAnswerFor(payload.message),
    };
  } else {
    console.log("[askTutor] calling backend API:", payload);
    const data = await request<ChatApiResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message: payload.message,
        session_id: payload.sessionId,
        profile: payload.profile && {
          subject: payload.profile.subject,
          level: payload.profile.level,
          style: payload.profile.style,
          language: payload.profile.language,
          student_name: payload.profile.studentName,
        },
      }),
    });
    response = { sessionId: data.session_id, answer: data.reply };
  }

  console.log("[askTutor] response:", response);
  return response;
}
