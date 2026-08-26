import type { AskTutorRequest, AskTutorResponse } from "../types";
import { mockAnswerFor } from "./mockData";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API === "true";
const MOCK_DELAY_MS = 400;

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(
      `${res.status} ${res.statusText}${body ? `: ${body}` : ""}`,
    );
  }

  return res.json() as Promise<T>;
}

/** POST /tutor/ask { classId, subjectId, question } -> { answer } */
export async function askTutor(
  payload: AskTutorRequest,
): Promise<AskTutorResponse> {
  console.log("[askTutor] request payload:", payload);

  let response: AskTutorResponse;
  if (USE_MOCK_API) {
    await delay(MOCK_DELAY_MS);
    response = { answer: mockAnswerFor(payload.question) };
  } else {
    console.log("[askTutor] calling backend API:", payload);
    response = await request<AskTutorResponse>("/tutor/ask", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  console.log("[askTutor] response:", response);
  return response;
}
