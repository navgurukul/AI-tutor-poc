import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { askTutorStream, prepareTutor, warmupTutor } from "../services/api";
import { useTutorTts } from "./tts/useTutorTts";
import { useTutorSpeechToText } from "./stt/useTutorSpeechToText";
import type { TutorLanguage } from "../config/languages";
import type {
  ChatMessage,
  Citation,
  ClientTurnMetrics,
  TutorProfile,
} from "../types";

export type TutorStage = "idle" | "listening" | "thinking" | "speaking" | "error";

interface UseTutorSessionArgs {
  subjectName: string;
  level: string;
  /**
   * A session the lobby already warmed, continued instead of starting fresh.
   *
   * This is the single largest thing separating a fast first question from a
   * slow one. Ollama reuses a cached prompt prefix only when the new prompt
   * *extends* the previous one; a question asked in a new session shares the
   * persona and pinned textbook and then forks, and a fork reuses nothing at
   * all. Measured 2026-09-09: 19.5s forking, 1.8s continuing.
   */
  primedSessionId?: string;
  /** Drives `profile.language` ("Reply in <name>.") and the STT engine. */
  language: TutorLanguage;
}

// Unique per message and stable across HMR reloads. A module-level counter
// resets on hot-reload while the `messages` state survives, so ids collide and a
// streamed reply lands on an earlier bubble instead of its own.
const nextId = (): string =>
  globalThis.crypto?.randomUUID?.() ??
  `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

// STT builds `transcript` as `prev + " " + chunk`, so it carries a leading space
// and can gather doubles where an interim tail is appended.
const collapseSpaces = (s: string) => s.replace(/\s+/g, " ").trim();

// gemma still sprinkles markdown (`* **bold:**`, `#`, backticks) into answers
// despite the prompt. Piper's phonemizer reads those symbols aloud ("तारांकन"
// for `*`), so scrub them before a sentence is spoken.
const stripForSpeech = (s: string) =>
  s
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s*[-*•]\s+/gm, "")
    // Numbered list markers ("1. ", "2) ") — otherwise Piper reads the lone
    // digit aloud ("एक") as its own utterance.
    .replace(/^\s*\d+[.)]\s+/gm, "")
    .replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/(\*|_)(.*?)\1/g, "$2")
    .replace(/[*_#>`]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

// The reply is spoken in clips as the model decodes: the first starts playing
// while the rest is still being written, and the backend TTS queue plays them
// back to back.
//
// Clip sizes RAMP, and every clip is capped. The model writes Hindi at ~12.7
// chars/s and the voice reads at ~13 chars/s, so once speech is flowing the two
// keep pace -- a silence only opens when the next clip is much LONGER than the
// one playing, because it has to be written in full (and synthesised) before it
// can start. The old rule was a short opener (18-28 chars) followed by whole
// sentences of 45+ chars with no cap, and a Hindi sentence often runs 90-160
// characters without a danda. Simulated 2026-09-11 on three real Hindi answers
// with rates measured on this box (synth ~0.02 s + 0.0198 s/char under load,
// speech ~0.7 s + chars/13.3):
//
//     total silence after first audio   12.2 / 5.0 / 7.6 s  ->  1.5 / 1.9 / 1.7 s
//     gap between clip 1 and clip 2      9.6 / 1.4 / 2.8 s  ->  0.4 / 0.5 / 0.5 s
//
// First audio is unchanged. The cost is more, shorter clips: a clip ends at a
// sentence end or a comma when one exists in range, and at a word boundary when
// none does -- a slightly flatter phrase ending, against multi-second holes.
//
// `min` is the shortest clip worth sending (below ~15 chars a clip plays out in
// a blink and leaves dead air); `max` is where it is cut at the last space if
// no boundary has appeared. The first entry is the opener: its cap is what sets
// time-to-first-audio (see git history for the 2026-09-09 measurements behind
// 18/28).
const SPEECH_CLIP_RAMP: ReadonlyArray<{ min: number; max: number }> = [
  { min: 18, max: 28 },
  { min: 20, max: 40 },
  { min: 24, max: 52 },
];
// Every clip after the ramp.
const SPEECH_CLIP_STEADY = { min: 30, max: 64 };

/**
 * Pulls every *complete* sentence off the front of a growing token buffer.
 *
 * A Latin terminator (.?!…) only counts when whitespace follows it, which is
 * what makes the sentence provably finished mid-stream and keeps "3.14" in one
 * piece. The Devanagari danda (। ॥) is unambiguous — it's only ever an
 * end-of-sentence mark — so it terminates immediately, even with no trailing
 * space; without this the whole Hindi/Marathi reply is one block and TTS can't
 * start until the stream ends. The unterminated tail stays in `rest` until more
 * tokens arrive, or until the stream ends and the caller flushes it.
 */
function drainSentences(
  buffer: string,
  minChars: number,
  breakOnClause = false,
  maxChars = 0,
): { sentences: string[]; rest: string } {
  const sentences: string[] = [];
  // A `.` right after a digit is a list marker ("1. ") or a decimal, not a
  // sentence end — the negative lookbehind keeps "ये है: 1." from being spoken
  // as its own fragment. The danda (। ॥) is always a sentence end.
  //
  // `breakOnClause` additionally treats a comma/semicolon/colon as a place to
  // stop. STALE UNTIL 2026-09-15: this used to be passed true for the opening
  // chunk only, on the reasoning that a mid-sentence pause is audible anywhere
  // but the very start. That was deliberately widened to every ramped clip on
  // 2026-09-11 (see SPEECH_CLIP_RAMP above) once simulation showed whole-
  // sentence-only clips left multi-second holes waiting for a 90-160 char
  // Hindi sentence to finish -- a slightly flatter mid-answer phrase ending
  // measured far better than that silence (gap after clip 1: 9.6/1.4/2.8s ->
  // 0.4/0.5/0.5s). Digits are excluded on both sides so "1,000" and "3:30"
  // stay intact.
  const boundary = breakOnClause
    ? /(?:(?<!\d)[.!?…]+["')\]]*(?=\s)|[।॥]+|(?<!\d)[,;:](?!\d)(?=\s))/g
    : /(?:(?<!\d)[.!?…]+["')\]]*(?=\s)|[।॥]+)/g;
  let rest = buffer;
  let searchFrom = 0;

  for (;;) {
    boundary.lastIndex = searchFrom;
    const match = boundary.exec(rest);
    if (!match) {
      // No boundary anywhere in what has been written so far. For the opening
      // chunk only (`maxChars` is 0 everywhere else), stop waiting once enough
      // text exists and cut at the last space that still leaves a chunk longer
      // than `minChars`. If the only spaces are too early, keep waiting —
      // a five-character opener plays out in a blink and leaves dead air.
      if (maxChars && rest.length >= maxChars) {
        const cut = rest.slice(0, maxChars).lastIndexOf(" ");
        if (cut >= minChars) {
          sentences.push(rest.slice(0, cut).trim());
          rest = rest.slice(cut);
        }
      }
      break;
    }

    const end = match.index + match[0].length;
    const candidate = rest.slice(0, end).trim();
    if (candidate.length < minChars) {
      // Keep it and look for the next boundary, so it's spoken as one phrase.
      searchFrom = end;
      continue;
    }

    sentences.push(candidate);
    rest = rest.slice(end);
    searchFrom = 0;
  }

  return { sentences, rest };
}

export function useTutorSession({
  subjectName,
  level,
  language,
  primedSessionId,
}: UseTutorSessionArgs) {
  const langName = language.name;

  // ONE profile object for the warm-up and for every turn. These must agree
  // exactly: the warm-up's whole purpose is to leave the system prompt in
  // Ollama's KV cache so the first question reuses it, and reuse is by prefix,
  // so any difference makes the warm-up worthless. Two call sites each building
  // their own literal is how they drift -- on 2026-09-09 the warm-up assembled
  // 526 prompt tokens and the first question 487, and turn 1 prefilled at
  // 31ms/token while turn 2 (which extended turn 1, so it did hit) managed 6.7.
  const profile = useMemo<TutorProfile>(
    () => ({ subject: subjectName, level, language: langName }),
    [subjectName, level, langName],
  );

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [stage, setStage] = useState<TutorStage>("idle");
  const [error, setError] = useState<string | null>(null);
  // The editable question box. STT drops its transcript here instead of firing
  // straight at the LLM, so the student can fix a misheard word — or just type —
  // before pressing Send.
  const [draft, setDraft] = useState("");
  const [isVoiceEnabled, setIsVoiceEnabled] = useState(true);
  // True once the page-load warm-up has settled — the model is resident, or the
  // attempt failed and the first question pays the cold start as it used to.
  const [isModelWarm, setIsModelWarm] = useState(false);
  const voiceEnabledRef = useRef(true);
  const wasListening = useRef(false);
  // Set by cancelTurn so the auto-submit effect drops that utterance instead of
  // sending it.
  const cancelledRef = useRef(false);
  // One submission per utterance, whichever path (Send or silence) triggers it.
  const submittingRef = useRef(false);
  // Seeded from the lobby's warm-up so the first question continues that
  // conversation. Empty when the tutor was opened directly (#tutor, or a reload
  // that skipped the lobby), in which case the first question pays the full
  // prefill the way it always did.
  const sessionIdRef = useRef<string | undefined>(primedSessionId || undefined);
  // The profile the lobby's session was primed for.
  //
  // COMPARED, never consumed. An earlier version flipped a "used" flag on the
  // first warm-up pass, which React StrictMode broke in dev: it invokes effects
  // twice on mount, so the second pass found the flag already spent, treated it
  // as a profile change, threw the primed session away and warmed again. The
  // chat page logged its own warm-up and the first question paid the full 22s
  // prefill the lobby existed to avoid (seen 2026-09-10).
  //
  // `profile` is memoised on [subject, level, language], so its identity is
  // stable across the double invoke and changes only when the persona really
  // does — which is exactly the condition we want.
  const primedForRef = useRef(primedSessionId ? profile : null);
  // A second, CONTENT-based guard (not identity-based like primedForRef
  // above), updated every time a warm-up actually succeeds -- fast-path or
  // real. Added 2026-09-14: a stray warm-up was observed firing mid-
  // conversation, live, ~18-20s of pure gemma2 prefill with nothing in the
  // chat UI to explain it, and every question for the next couple of turns
  // ran slow from the CPU contention it left behind. The exact trigger
  // (something making `profile`'s useMemo produce a new object, or a
  // remount) was not pinned down from static reading alone -- what this adds
  // is a check that survives EITHER: if we already hold a real session id and
  // its warmed profile's actual VALUES still match, warming again is refused
  // regardless of why the effect re-ran. A console line names the mismatch
  // if it ever legitimately fires again, so a recurrence is diagnosable
  // instead of invisible.
  const warmedProfileRef = useRef<{ subject: string; level: string; language: string } | null>(
    primedSessionId ? { subject: subjectName, level, language: langName } : null,
  );
  // Lets Stop tear down an in-flight generation, which also stops the model
  // decoding server-side instead of burning CPU on an answer nobody will hear.
  const streamAbortRef = useRef<AbortController | null>(null);

  // Set by "Stop audio" — silences the rest of this answer's speech while the
  // text keeps streaming in. Cleared at the start of the next turn.
  const speechStoppedRef = useRef(false);

  // Pipeline timing: voice captured -> first token -> first audio -> speech done.
  const turnStartRef = useRef<number | null>(null);
  const speakQueueStartRef = useRef<number | null>(null);
  const firstAudioLoggedRef = useRef(false);
  const allChunksQueuedRef = useRef(false);

  // Transcription is timed from the mic closing, not from the mic opening: the
  // time in between is the student talking, which is not the tutor being slow.
  // What we want is the batch decode the student waits through in silence.
  const sttCloseRef = useRef<number | null>(null);
  // Survives into the next turn on purpose — the student dictates, edits the
  // draft, then sends, so this was measured before `askAndSpeak` existed.
  // Cleared once consumed, so a typed follow-up doesn't inherit it.
  const lastSttMsRef = useRef<number | undefined>(undefined);

  const {
    startListening,
    stopListening,
    resetTranscript,
    transcript,
    interimTranscript,
    isListening,
    isTranscribing,
    supported: sttSupported,
    isLoading: sttLoading,
    progress: sttProgress,
    error: sttError,
  } = useTutorSpeechToText(language);

  const {
    speak,
    endTurn: endSpeech,
    cancel: cancelSpeech,
    primeAudio,
    isSupported: isSpeechSupported,
    isReady: isVoiceReady,
    isSpeaking: isPlaying,
    voiceError,
  } = useTutorTts(language);

  // The id of the tutor bubble for the turn in flight, so the streaming update
  // always targets the right message.
  const replyIdRef = useRef<string | null>(null);

  // The backend sends its sources frame *before* the first token, so the reply
  // bubble does not exist yet when they arrive. Parking them here and attaching
  // them as the bubble is created avoids rendering an empty bubble that shows
  // citations for an answer that has not started.
  const pendingSourcesRef = useRef<Citation[] | undefined>(undefined);

  // Metrics arrive with the very last frame, so unlike sources they are parked
  // here only for the width of one setState — but through the same ref, so the
  // bubble is written from one place and cannot end up with an answer from this
  // turn and numbers from the last one.
  const pendingMetricsRef = useRef<ClientTurnMetrics | undefined>(undefined);

  const setReplyText = useCallback((text: string) => {
    const id = replyIdRef.current;
    if (!id) return;
    setMessages((prev) => {
      const patch = {
        text,
        sources: pendingSourcesRef.current,
        metrics: pendingMetricsRef.current,
      };
      const index = prev.findIndex((m) => m.id === id);
      if (index === -1) return [...prev, { id, role: "tutor", ...patch }];
      const next = [...prev];
      next[index] = { ...next[index], ...patch };
      return next;
    });
  }, []);

  /**
   * Merge late-arriving numbers into the reply that is already on screen.
   *
   * The speech timings cannot ride the `done` frame like the rest: the answer
   * has finished streaming long before the last sentence finishes playing. So
   * the bubble is written once with the server's numbers, then patched as the
   * voice reaches each milestone.
   */
  const patchMetrics = useCallback((patch: Partial<ClientTurnMetrics>) => {
    const id = replyIdRef.current;
    if (!id) return;
    pendingMetricsRef.current = pendingMetricsRef.current
      ? { ...pendingMetricsRef.current, ...patch }
      : undefined;
    setMessages((prev) => {
      const index = prev.findIndex((m) => m.id === id);
      if (index === -1 || !prev[index].metrics) return prev;
      const next = [...prev];
      next[index] = {
        ...next[index],
        metrics: { ...next[index].metrics!, ...patch },
      };
      return next;
    });
  }, []);

  // Warm-load the LLM the moment the session mounts, and again whenever the
  // language changes. Ollama otherwise loads the weights (and, on a language
  // switch, re-processes the whole new system prompt) lazily on the first
  // question. Re-gating `isModelWarm` here keeps the mic disabled until Ollama
  // has the new-language prompt prefix cached, so the first turn after a switch
  // isn't the one that pays ~10-16s.
  useEffect(() => {
    // The MAIN guard: if we already hold a real session AND its warmed
    // profile's VALUES still match this render's, there is nothing to do —
    // regardless of WHY this effect re-ran (an identity change in `profile`
    // that isn't a real content change, a re-render, anything else). This is
    // what actually stops a stray re-warm; the identity check just below is
    // only the FIRST warm-up's fast path, for the moment before any session
    // exists yet and there is nothing here for this check to compare against.
    const alreadyWarmed =
      warmedProfileRef.current !== null &&
      warmedProfileRef.current.subject === subjectName &&
      warmedProfileRef.current.level === level &&
      warmedProfileRef.current.language === langName;
    if (sessionIdRef.current && alreadyWarmed) {
      setIsModelWarm(true);
      return;
    }
    // The lobby already warmed this exact profile and handed us its session.
    // Warming again would be worse than redundant: this call opens a NEW
    // session, so it would leave Ollama's cache holding a different branch than
    // the one the first question continues, and hand back the 19.5s prefill the
    // lobby existed to avoid.
    if (primedSessionId && primedForRef.current === profile) {
      sessionIdRef.current = primedSessionId;
      warmedProfileRef.current = { subject: subjectName, level, language: langName };
      setIsModelWarm(true);
      return;
    }
    // Reached only when the profile genuinely changed (or this is the very
    // first mount with no primed session). The old session carries the old
    // persona and the old language's history, so continuing it would put the
    // wrong instructions in front of every answer — start a fresh one.
    if (sessionIdRef.current) {
      // Not the first warm-up: something changed. Named here, once, so a
      // recurrence of the 2026-09-14 stray-rewarm symptom is diagnosable
      // from the console instead of an unexplained multi-second stall.
      console.warn(
        "[warm-up] re-warming an existing session -- profile changed from " +
          `${JSON.stringify(warmedProfileRef.current)} to ` +
          `${JSON.stringify({ subject: subjectName, level, language: langName })}` +
          ` (primedSessionId=${primedSessionId || "none"})`,
      );
    }
    sessionIdRef.current = undefined;
    let active = true;
    const controller = new AbortController();
    const startedAt = performance.now();
    setIsModelWarm(false);
    void warmupTutor(profile, controller.signal)
      .then((result) => {
        if (result) {
          console.log(
            `[timing] model warm-up: ${(performance.now() - startedAt).toFixed(0)}ms ` +
              `(ollama load_duration ${result.loadDurationMs}ms, ` +
              `prompt ${result.promptTokens} tok)`,
          );
        }
      })
      .finally(() => {
        if (active) {
          setIsModelWarm(true);
          warmedProfileRef.current = { subject: subjectName, level, language: langName };
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [profile, primedSessionId, subjectName, level, langName]);

  // A language switch is a fresh conversation: drop the cross-language history
  // so the first turn in the new language only re-processes the system prompt
  // (not a pile of messages in the other language), and the model isn't
  // answering in one language with context in another.
  const prevLangCodeRef = useRef(language.code);
  useEffect(() => {
    if (prevLangCodeRef.current === language.code) return;
    prevLangCodeRef.current = language.code;
    streamAbortRef.current?.abort();
    cancelSpeech();
    sessionIdRef.current = undefined;
    submittingRef.current = false;
    cancelledRef.current = false;
    setMessages([]);
    resetTranscript();
    setDraft("");
    setStage("idle");
  }, [language.code, resetTranscript, cancelSpeech]);

  // Read the likely passage for a question into the backend's cache before
  // Send, from whatever is in the draft box -- typed input, or the transcript
  // once the mic closes. See services/api.ts's `prepareTutor`.
  //
  // Deliberately NOT also triggered from the STT engine's live interim
  // transcript while still listening, even though that would give a spoken
  // question a bigger head start. Measured 2026-09-14: doing so put a prepare
  // call's retrieval + Ollama prime (CPU-heavy) squarely in the same window as
  // IndicConformer's own periodic re-decode of the growing clip -- two
  // slowdowns lined up back to back in the backend log against two slow
  // transcriptions the student saw (9.9s and 13.9s, against a normal
  // ~0.3-1.2s). This is the exact failure this project already learned to
  // avoid (EXP-011: a background job during testing turned a ~6s turn into
  // 43-56s) -- STT just never asks for the CPU explicitly, so it lost that
  // contention silently instead of erroring. Preparing only from the draft
  // means it never runs until STT's own decode has already finished.
  //
  // Debounced so a burst (fast typing) fires one request rather than one per
  // keystroke; sessionIdRef is read at fire time, not captured, since it is a
  // ref and often still empty when this effect is first wired up.
  const PREPARE_DEBOUNCE_MS = 700;
  const prepareTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The last text actually sent for preparing, so a value that hasn't changed
  // (the draft box re-rendering, an interim tick with nothing new) doesn't
  // requeue the same guess. Safe to leave unreset between utterances: if a new
  // question's opening words happen to exactly match what was already
  // prepared, the worst case is that ONE utterance falls back to the normal,
  // un-primed turn -- never a wrong answer.
  const preparedForRef = useRef("");

  const schedulePrepare = useCallback(
    (text: string) => {
      const trimmed = collapseSpaces(text);
      if (!trimmed || trimmed === preparedForRef.current) return;
      if (prepareTimerRef.current) clearTimeout(prepareTimerRef.current);
      prepareTimerRef.current = setTimeout(() => {
        prepareTimerRef.current = null;
        preparedForRef.current = trimmed;
        prepareTutor(trimmed, sessionIdRef.current, profile);
      }, PREPARE_DEBOUNCE_MS);
    },
    [profile],
  );

  useEffect(() => {
    schedulePrepare(draft);
  }, [draft, schedulePrepare]);

  useEffect(
    () => () => {
      if (prepareTimerRef.current) clearTimeout(prepareTimerRef.current);
    },
    [],
  );

  const askAndSpeak = useCallback(
    async (question: string) => {
      const turnStart = performance.now();
      turnStartRef.current = turnStart;
      speakQueueStartRef.current = null;
      firstAudioLoggedRef.current = false;
      allChunksQueuedRef.current = false;
      speechStoppedRef.current = false;
      pendingSourcesRef.current = undefined;
      pendingMetricsRef.current = undefined;

      // Stop any speech still playing from a previous turn.
      cancelSpeech();

      setStage("thinking");
      setMessages((prev) => [...prev, { id: nextId(), role: "user", text: question }]);

      const replyId = nextId();
      replyIdRef.current = replyId;
      const controller = new AbortController();
      streamAbortRef.current = controller;

      let answer = "";
      let unspoken = "";
      // Clips queued so far this turn -- indexes SPEECH_CLIP_RAMP.
      let clipIndex = 0;
      let firstTokenAt: number | null = null;
      // Kept alongside `answer` rather than read back off the ref: TypeScript
      // cannot see that a callback wrote to `.current`, and narrows it to the
      // `undefined` it was reset to at the top of the turn.
      let turnMetrics: ClientTurnMetrics | undefined;

      // Diagnostic only (2026-09-15, chasing a reported gap between clip 1 and
      // clip 2): when this queues is how long the CLIP took to become
      // available, not how long it takes to play or synthesize -- if the gap
      // the student hears tracks this, the model is falling behind the ramp's
      // assumed writing pace; if it doesn't, look at synthesis/playback
      // instead (useBackendTts's own queue).
      let lastClipQueuedAt = turnStart;
      const enqueueSpeech = (text: string) => {
        if (!voiceEnabledRef.current || speechStoppedRef.current) return;
        const spoken = stripForSpeech(text);
        if (!spoken) return;
        const now = performance.now();
        if (speakQueueStartRef.current === null) {
          speakQueueStartRef.current = now;
          console.log(
            `[timing] voice -> first sentence queued: ${(now - turnStart).toFixed(0)}ms ` +
              `(${spoken.length} chars: "${spoken.slice(0, 60)}${spoken.length > 60 ? "…" : ""}")`,
          );
        } else {
          console.log(
            `[timing] clip ${clipIndex + 1} queued: +${(now - lastClipQueuedAt).toFixed(0)}ms since previous clip ` +
              `(${spoken.length} chars: "${spoken.slice(0, 60)}${spoken.length > 60 ? "…" : ""}")`,
          );
        }
        lastClipQueuedAt = now;
        // The speech queue plays phrases in order, gaplessly.
        speak(spoken);
      };

      try {
        await askTutorStream(
          {
            message: question,
            sessionId: sessionIdRef.current,
            profile,
          },
          {
            onStart: (sessionId) => {
              sessionIdRef.current = sessionId;
            },
            onSources: (sources) => {
              pendingSourcesRef.current = sources;
            },
            onToken: (token) => {
              if (firstTokenAt === null) {
                firstTokenAt = performance.now();
                console.log(
                  `[timing] voice -> first token: ${(firstTokenAt - turnStart).toFixed(0)}ms`,
                );
                setStage("speaking");
              }

              answer += token;
              unspoken += token;

              // Render the partial answer at full speed, in parallel with the
              // voice — which speaks a sentence at a time and keeps pace.
              setReplyText(answer);

              // Cut the next clip by its place in the ramp -- see
              // SPEECH_CLIP_RAMP for why clips grow gradually and stay capped.
              for (;;) {
                const clip = SPEECH_CLIP_RAMP[clipIndex] ?? SPEECH_CLIP_STEADY;
                const { sentences, rest } = drainSentences(
                  unspoken,
                  clip.min,
                  true,
                  clip.max,
                );
                if (sentences.length === 0) break;
                // One clip at a time, so each takes the size for its own place
                // in the ramp rather than all sharing the first one's.
                enqueueSpeech(sentences[0]);
                clipIndex += 1;
                unspoken = sentences.slice(1).join(" ") + rest;
              }
            },
            onDone: ({ sessionId, answer: finalAnswer, metrics }) => {
              sessionIdRef.current = sessionId;
              // The server's reply is the same text, trimmed; prefer it so the
              // bubble doesn't keep stray leading/trailing whitespace.
              answer = finalAnswer || answer;
              // The server's clock starts when the request arrives. By then the
              // student has already waited through capture and transcription,
              // so the two browser-side numbers are added here rather than
              // inferred from the server's — nothing on the backend can see them.
              if (metrics) {
                turnMetrics = {
                  ...metrics,
                  client_ttft_ms:
                    firstTokenAt === null
                      ? undefined
                      : Math.round(firstTokenAt - turnStart),
                  client_total_ms: Math.round(performance.now() - turnStart),
                  stt_ms: lastSttMsRef.current,
                };
                pendingMetricsRef.current = turnMetrics;
                // Consumed. A typed follow-up must not inherit the timing of
                // whatever was last dictated.
                lastSttMsRef.current = undefined;
              }
              setReplyText(answer);
            },
          },
          controller.signal,
        );

        console.log(
          `[timing] voice -> full reply: ${(performance.now() - turnStart).toFixed(0)}ms`,
        );

        // The server-side split, alongside the browser-side one above. Retrieval
        // is milliseconds and prefill is seconds, so the line that matters when
        // tuning RAG is prefill against the context tokens that caused it.
        const m = turnMetrics;
        if (m) {
          console.log(
            `[timing] server: total ${m.total_ms.toFixed(0)}ms · ` +
              `retrieval ${m.retrieval_ms.toFixed(0)}ms ` +
              `(${m.retrieval.returned} passages, ${m.retrieval.context_tokens} tokens) · ` +
              `prefill ${m.prefill_ms}ms (${m.prompt_tokens} tok) · ` +
              `decode ${m.decode_ms}ms (${m.completion_tokens} tok @ ` +
              `${m.tokens_per_second} tok/s)`,
          );
        }

        // The last sentence has no trailing whitespace to prove it ended, so it
        // is always still sitting in the tail here.
        const tail = unspoken.trim();
        if (tail) enqueueSpeech(tail);

        // Nothing further will be queued, so the voice can stop holding clips
        // back for a cushion — a one-clip answer would otherwise never play.
        endSpeech();

        allChunksQueuedRef.current = true;
        setStage("idle");

        // Voice off / nothing queued: no "fully spoken" event is coming.
        if (speakQueueStartRef.current === null) turnStartRef.current = null;
      } catch (err) {
        // Stop was pressed — the partial answer stays on screen, no error shown.
        if ((err as Error)?.name === "AbortError") {
          turnStartRef.current = null;
          return;
        }
        setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
        setStage("error");
        turnStartRef.current = null;
      } finally {
        if (streamAbortRef.current === controller) streamAbortRef.current = null;
        submittingRef.current = false;
      }
    },
    [profile, speak, endSpeech, cancelSpeech, setReplyText],
  );

  // The single path from a captured question to a turn. Guarded so the mic's
  // "Send" and the silence path can't both fire for one utterance.
  const submitQuestion = useCallback(
    (question: string) => {
      if (submittingRef.current) return;
      submittingRef.current = true;
      resetTranscript();
      void askAndSpeak(question);
    },
    [resetTranscript, askAndSpeak],
  );

  // "Send" on the draft box: hand the reviewed/typed text to the one submit
  // path, then clear the box.
  const sendDraft = useCallback(() => {
    const question = collapseSpaces(draft);
    if (!question) return;
    setDraft("");
    submitQuestion(question);
  }, [draft, submitQuestion]);

  // Logs time-to-first-audio and total voice->fully-spoken duration by watching
  // the isSpeaking flag, since speak() returns as soon as the phrase is queued.
  useEffect(() => {
    const turnStart = turnStartRef.current;
    if (turnStart === null) return;

    if (isPlaying && !firstAudioLoggedRef.current && speakQueueStartRef.current !== null) {
      firstAudioLoggedRef.current = true;
      const now = performance.now();
      console.log(
        `[timing] first sentence queued -> first audio: ${(now - speakQueueStartRef.current).toFixed(0)}ms ` +
          `(voice -> first audio total: ${(now - turnStart).toFixed(0)}ms)`,
      );
      patchMetrics({
        tts_first_audio_ms: Math.round(now - speakQueueStartRef.current),
      });
    }

    if (!isPlaying && firstAudioLoggedRef.current && allChunksQueuedRef.current) {
      const now = performance.now();
      console.log(`[timing] voice -> fully spoken total: ${(now - turnStart).toFixed(0)}ms`);
      patchMetrics({ spoken_total_ms: Math.round(now - turnStart) });
      turnStartRef.current = null;
    }
  }, [isPlaying, patchMetrics]);

  // Once the mic closes — the silence timeout or a manual "Stop" (finishTurn) —
  // move what was heard into the editable draft box instead of sending it. The
  // student reviews it and presses Send (sendDraft). For a batch STT engine
  // (IndicConformer) the transcript isn't ready until `isTranscribing` clears,
  // so hold off until then. A second dictation appends to whatever is already in
  // the box, spoken or typed.
  useEffect(() => {
    if (isTranscribing) return;

    if (wasListening.current && !isListening) {
      wasListening.current = false;
      const cancelled = cancelledRef.current;
      cancelledRef.current = false;
      const heard = cancelled
        ? ""
        : collapseSpaces(`${transcript} ${interimTranscript}`);
      resetTranscript();
      setStage("idle");
      if (heard) {
        setDraft((prev) =>
          collapseSpaces(prev ? `${prev} ${heard}` : heard),
        );
      }
      return;
    }

    wasListening.current = isListening;
  }, [isListening, isTranscribing, transcript, interimTranscript, resetTranscript]);

  // Show the "working on it" state during a batch transcribe, and disable the
  // mic — unless the user just cancelled, in which case stay idle.
  useEffect(() => {
    if (isTranscribing && !cancelledRef.current) setStage("thinking");
  }, [isTranscribing]);

  // Time the batch decode: the mic closing starts the clock, the transcript
  // arriving stops it. The streaming browser engine never sets isTranscribing,
  // so it records ~0 here, which is the truth — it has already decoded.
  useEffect(() => {
    if (isListening) {
      sttCloseRef.current = null;
      return;
    }
    if (sttCloseRef.current === null) {
      sttCloseRef.current = performance.now();
      return;
    }
    if (!isTranscribing) {
      const elapsed = performance.now() - sttCloseRef.current;
      sttCloseRef.current = null;
      lastSttMsRef.current = Math.round(elapsed);
      console.log(`[timing] transcription: ${elapsed.toFixed(0)}ms`);
    }
  }, [isListening, isTranscribing]);

  useEffect(() => {
    if (sttError) setError(sttError);
  }, [sttError]);

  useEffect(() => {
    if (isListening) setStage("listening");
  }, [isListening]);

  const startTurn = useCallback(() => {
    setError(null);
    cancelledRef.current = false;
    submittingRef.current = false;
    // This runs from the mic tap — the one user gesture we get — so unlock the
    // audio pipeline now, or the browser keeps the AudioContext suspended and
    // the MMS voice is silent.
    primeAudio();
    resetTranscript();
    startListening();
  }, [primeAudio, resetTranscript, startListening]);

  const cancelTurn = useCallback(() => {
    cancelledRef.current = true;
    stopListening();
    resetTranscript();
    setStage("idle");
  }, [stopListening, resetTranscript]);

  /**
   * The mic's "Send": stop capturing now instead of waiting out the silence
   * timeout. The auto-submit effect picks it up once the transcript is ready
   * (immediately for the browser engine, after decoding for IndicConformer).
   */
  const finishTurn = useCallback(() => {
    stopListening();
  }, [stopListening]);

  const silenceSpeech = useCallback(() => {
    cancelSpeech();
    // Drop the pending timing measurement — this turn never finished speaking.
    turnStartRef.current = null;
  }, [cancelSpeech]);

  /**
   * "Stop audio": silences the voice for the rest of this answer and blocks any
   * remaining sentences from being spoken — but lets the LLM response finish
   * streaming into the chat bubble.
   */
  const stopSpeaking = useCallback(() => {
    speechStoppedRef.current = true;
    silenceSpeech();
  }, [silenceSpeech]);

  /**
   * Persistent on/off for spoken answers. Turning it off also silences whatever
   * is playing right now, so one tap always ends the audio — but it lets the
   * answer finish streaming into the transcript.
   */
  const toggleVoice = useCallback(() => {
    // Read from the ref, not state, so the side effect stays outside the
    // setState updater (which React may invoke twice under StrictMode).
    const nowEnabled = !voiceEnabledRef.current;
    voiceEnabledRef.current = nowEnabled;
    setIsVoiceEnabled(nowEnabled);
    if (!nowEnabled) silenceSpeech();
  }, [silenceSpeech]);

  return {
    messages,
    stage,
    error,
    draft,
    setDraft,
    sendDraft,
    isListening,
    isTranscribing,
    transcript,
    interimTranscript,
    isPlaying,
    isVoiceReady,
    isSpeechSupported,
    voiceError,
    isModelWarm,
    sttSupported,
    sttLoading,
    sttDownloadProgress: sttProgress,
    isVoiceEnabled,
    startTurn,
    cancelTurn,
    finishTurn,
    stopSpeaking,
    toggleVoice,
  };
}
