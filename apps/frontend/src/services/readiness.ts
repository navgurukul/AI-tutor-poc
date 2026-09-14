import { API_BASE_URL } from "./api";

/**
 * Readiness probes for the things a turn cannot start without.
 *
 * These exist because of what the models cost on the target hardware. The
 * backend loads each one lazily on first use, so without a page that asks for
 * them up front, the *student's first question* is the request that pays: the
 * IndicConformer recogniser, the Piper voice, and — by far the largest — the
 * LLM reading the persona and the pinned textbook before it writes a token.
 *
 * Measured 2026-09-09 on the 8 GB target: a cold first turn was 18.5s to first
 * token while every warm turn after it was 3.6-3.9s. That gap is not the model
 * being slow; it is the first turn doing setup work in front of the student.
 * The setup page moves it to a moment where waiting is expected.
 *
 * Each probe doubles as the trigger for the load it is checking, which is why
 * they are worth calling even when the answer is predictable.
 */

export interface ReadinessResult {
  ready: boolean;
  /** Why it isn't ready — safe to show a teacher, not a stack trace. */
  detail?: string;
}

async function probe(path: string, language: string): Promise<ReadinessResult> {
  try {
    const res = await fetch(
      `${API_BASE_URL}${path}?language=${encodeURIComponent(language)}`,
    );
    if (!res.ok) {
      return { ready: false, detail: `Backend returned ${res.status}.` };
    }
    const data = (await res.json()) as { ready?: boolean; detail?: string };
    return {
      ready: Boolean(data.ready),
      detail: data.detail ?? (data.ready ? undefined : "Not installed."),
    };
  } catch {
    return { ready: false, detail: "Backend unreachable." };
  }
}

/** Is offline speech recognition installed for this language, and loaded? */
export function checkSpeechToText(language: string): Promise<ReadinessResult> {
  return probe("/api/stt", language);
}

/** Is an offline Piper voice installed for this language, and loaded? */
export function checkTextToSpeech(language: string): Promise<ReadinessResult> {
  return probe("/api/tts", language);
}
