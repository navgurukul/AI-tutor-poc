import { useCallback, useEffect, useRef, useState } from "react";
// Speech runs on the backend through sherpa-onnx, fully offline: /api/stt
// (Whisper base.en) and /api/tts (a Piper voice). The browser records the mic
// and plays the WAVs it gets back; it downloads no models and never touches the
// Web Speech API, which streams to Google unless Chrome has its on-device pack.
import { useTutorSpeechToText } from "./stt/useTutorSpeechToText";
import { useTutorTts } from "./tts/useTutorTts";
import { DEFAULT_LANGUAGE } from "../config/languages";
import { askTutorStream, fetchGroundedness, warmupTutor,
  reportTurnTimings,
} from "../services/api";
import type { ChatMessage, Citation, TurnMetrics } from "../types";

export type TutorStage = "idle" | "listening" | "thinking" | "speaking" | "error";

interface UseTutorSessionArgs {
  subjectName: string;
  level: string;
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

// The backend synthesizes each speak() call as one Piper pass before any of it
// plays, so the reply is handed over one sentence at a time as the backend streams
// tokens: the first sentence starts playing while the model is still decoding
// the rest. Fragments shorter than this are merged into the sentence that
// follows so they aren't their own synthesis pass.
const MIN_SPEECH_CHARS = 12;

/**
 * Pulls every *complete* sentence off the front of a growing token buffer.
 *
 * A terminator only counts when whitespace follows it, which is what makes the
 * sentence provably finished mid-stream — it also keeps "3.14" and the like in
 * one piece. The unterminated tail stays in `rest` until more tokens arrive, or
 * until the stream ends and the caller flushes it.
 */
function drainSentences(buffer: string): { sentences: string[]; rest: string } {
  const sentences: string[] = [];
  const boundary = /[.!?]+["')\]]*(?=\s)/g;
  let rest = buffer;
  let searchFrom = 0;

  for (;;) {
    boundary.lastIndex = searchFrom;
    const match = boundary.exec(rest);
    if (!match) break;

    const end = match.index + match[0].length;
    const candidate = rest.slice(0, end).trim();
    if (candidate.length < MIN_SPEECH_CHARS) {
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

// The very first thing sent to Piper is a short phrase, not a whole sentence:
// synthesis is ~1.5s fixed overhead + ~60ms/char, so a ~20-char opener is
// audible several seconds sooner than a full first sentence. Only used while
// drainSentences has no complete sentence yet; every chunk after it is a full
// sentence.
//   1. a clause boundary (comma/semicolon/colon/dash) once ~14+ chars in, or
//   2. once ~22+ chars have arrived, the next word end.
// Trailing whitespace is required so "3,000" and mid-word hyphens stay whole.
const OPENING_CLAUSE = /^[\s\S]{14,}?[,;:—-](?=\s)/;
const OPENING_WORDS = /^[\s\S]{22,}?\S(?=\s)/;

function takeFirstFragment(
  buffer: string,
): { fragment: string; rest: string } | null {
  const match = OPENING_CLAUSE.exec(buffer) ?? OPENING_WORDS.exec(buffer);
  if (!match) return null;
  return { fragment: match[0].trim(), rest: buffer.slice(match[0].length) };
}

export function useTutorSession({ subjectName, level }: UseTutorSessionArgs) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [stage, setStage] = useState<TutorStage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [isVoiceEnabled, setIsVoiceEnabled] = useState(true);
  // True once the page-load warm-up has settled — the model is resident, or the
  // attempt failed and the first question pays the cold start as it used to.
  const [isModelWarm, setIsModelWarm] = useState(false);
  const voiceEnabledRef = useRef(true);
  const wasListening = useRef(false);
  // finishTurn (the mic's "Send") owns the outcome of a listening session, so the
  // silence-timeout effect must stay out of it; the timeout path leaves this
  // false and lets the effect submit.
  const listeningHandledRef = useRef(false);
  // One submission per utterance, whichever path (Send or timeout) calls it.
  const submittingRef = useRef(false);
  const sessionIdRef = useRef<string | undefined>(undefined);
  // Lets Stop tear down an in-flight generation, which also stops the model
  // decoding server-side instead of burning CPU on an answer nobody will hear.
  const streamAbortRef = useRef<AbortController | null>(null);

  // Set by "Stop audio" — silences the rest of this answer's speech while the
  // text keeps streaming in. Cleared at the start of the next turn.
  const speechStoppedRef = useRef(false);

  // Pipeline timing: voice captured -> first token -> first audio -> speech done.
  const turnStartRef = useRef<number | null>(null);
  // The backend issues a turn id on the start frame; these rows join to
  // turns-backend.csv on it. Held in refs because the values arrive from
  // several callbacks across the life of one turn.
  const turnIdRef = useRef<string | null>(null);
  const clientTimingRef = useRef<{
    ttft?: number; firstSentence?: number; firstAudio?: number;
    fullReply?: number; chars?: number;
  }>({});
  const speakQueueStartRef = useRef<number | null>(null);
  // Length of the opening fragment. The wait between queueing it and hearing
  // it is a steady ~1.1s on the target laptop; without the character count
  // there is no way to split that into Piper's fixed per-call overhead and
  // its per-character synthesis cost, i.e. no way to know which to attack.
  const firstChunkCharsRef = useRef(0);
  const firstAudioLoggedRef = useRef(false);
  const allChunksQueuedRef = useRef(false);

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
  } = useTutorSpeechToText(DEFAULT_LANGUAGE);

  const {
    speak,
    endTurn: endSpeech,
    cancel: cancelSpeech,
    isReady: isVoiceReady,
    isSpeaking: isPlaying,
    voiceError,
  } = useTutorTts(DEFAULT_LANGUAGE);

  // The id of the tutor bubble for the turn in flight, so the streaming update
  // always targets the right message.
  const replyIdRef = useRef<string | null>(null);

  // The backend sends its sources frame *before* the first token, so the reply
  // bubble does not exist yet when they arrive. Parking them here and attaching
  // them as the bubble is created avoids rendering an empty bubble that shows
  // citations for an answer that has not started.
  const pendingSourcesRef = useRef<Citation[] | undefined>(undefined);

  const setReplyText = useCallback((text: string) => {
    const id = replyIdRef.current;
    if (!id) return;
    setMessages((prev) => {
      const index = prev.findIndex((m) => m.id === id);
      if (index === -1)
        return [
          ...prev,
          {
            id,
            role: "tutor",
            text,
            sources: pendingSourcesRef.current,
            turnId: turnIdRef.current ?? undefined,
          },
        ];
      const next = [...prev];
      next[index] = {
        ...next[index],
        text,
        sources: pendingSourcesRef.current,
        turnId: turnIdRef.current ?? undefined,
      };
      return next;
    });
  }, []);

  /** Attach a gold-set turn's groundedness to the bubble it belongs to. */
  const setReplyGroundedness = useCallback(
    (id: string, groundedness: ChatMessage["groundedness"]) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, groundedness } : m)),
      );
    },
    [],
  );

  /** Attach the turn's cost once the reply has finished streaming. */
  const setReplyMetrics = useCallback((metrics: TurnMetrics) => {
    const id = replyIdRef.current;
    if (!id) return;
    setMessages((prev) => {
      const index = prev.findIndex((m) => m.id === id);
      if (index === -1) return prev;
      const next = [...prev];
      next[index] = { ...next[index], metrics };
      return next;
    });
  }, []);

  // Warm-load the LLM the moment the session mounts, in parallel with the Piper
  // voice model downloading above. Ollama otherwise loads the weights lazily on
  // the first question (~10s of silence on CPU); this pays that cost while the
  // student is still reading the screen and reaching for the mic.
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const startedAt = performance.now();
    void warmupTutor({ subject: subjectName, level }, controller.signal)
      .then((result) => {
        if (result) {
          console.log(
            `[timing] model warm-up: ${(performance.now() - startedAt).toFixed(0)}ms ` +
              `(ollama load_duration ${result.loadDurationMs}ms)`,
          );
        }
      })
      .finally(() => {
        if (active) setIsModelWarm(true);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [subjectName, level]);

  const askAndSpeak = useCallback(
    async (question: string) => {
      const turnStart = performance.now();
      turnStartRef.current = turnStart;
      speakQueueStartRef.current = null;
      firstAudioLoggedRef.current = false;
      firstChunkCharsRef.current = 0;
      allChunksQueuedRef.current = false;
      speechStoppedRef.current = false;
      pendingSourcesRef.current = undefined;

      // Drop anything still queued or playing from a previous turn.
      cancelSpeech();

      setStage("thinking");
      setMessages((prev) => [...prev, { id: nextId(), role: "user", text: question }]);

      const replyId = nextId();
      replyIdRef.current = replyId;
      const controller = new AbortController();
      streamAbortRef.current = controller;

      let answer = "";
      let unspoken = "";
      let firstTokenAt: number | null = null;
      let groundednessPending = false;
      const enqueueSpeech = (text: string) => {
        if (!voiceEnabledRef.current || speechStoppedRef.current) return;
        if (speakQueueStartRef.current === null) {
          speakQueueStartRef.current = performance.now();
          firstChunkCharsRef.current = text.length;
          clientTimingRef.current.firstSentence = Math.round(
            speakQueueStartRef.current - (turnStartRef.current ?? speakQueueStartRef.current),
          );
          console.log(
            `[timing] voice -> first sentence queued: ${(speakQueueStartRef.current - turnStart).toFixed(0)}ms ` +
              `(${text.length} chars: "${text.slice(0, 60)}${text.length > 60 ? "…" : ""}")`,
          );
        }
        // Queued in order by the TTS hook, which fetches and plays them back to back.
        speak(text);
      };

      try {
        await askTutorStream(
          {
            message: question,
            sessionId: sessionIdRef.current,
            profile: { subject: subjectName, level },
          },
          {
            onStart: (sessionId, turnId) => {
              sessionIdRef.current = sessionId;
              turnIdRef.current = turnId ?? null;
              clientTimingRef.current = {};
            },
            onSources: (sources) => {
              pendingSourcesRef.current = sources;
            },
            onToken: (token) => {
              if (firstTokenAt === null) {
                firstTokenAt = performance.now();
                clientTimingRef.current.ttft = Math.round(firstTokenAt - turnStart);
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

              const { sentences, rest } = drainSentences(unspoken);
              unspoken = rest;
              for (const sentence of sentences) enqueueSpeech(sentence);

              // Nothing queued yet and still no complete sentence — start the
              // voice on a short opening phrase so audio doesn't wait for a
              // whole first sentence (and then Piper's slow first pass on top).
              if (speakQueueStartRef.current === null && sentences.length === 0) {
                const frag = takeFirstFragment(unspoken);
                if (frag) {
                  unspoken = frag.rest;
                  enqueueSpeech(frag.fragment);
                }
              }
            },
            onDone: ({ sessionId, answer: finalAnswer, groundednessPending: pending }) => {
              sessionIdRef.current = sessionId;
              groundednessPending = !!pending;
              // The server's reply is the same text, trimmed; prefer it so the
              // bubble doesn't keep stray leading/trailing whitespace.
              answer = finalAnswer || answer;
              setReplyText(answer);
            },
          },
          controller.signal,
        );

        const fullReplyAt = performance.now();
        console.log(
          `[timing] voice -> full reply: ${(fullReplyAt - turnStart).toFixed(0)}ms`,
        );
        // Same numbers the console has always carried, now also on the reply
        // itself so they can be read on a device with no DevTools open.
        setReplyMetrics({
          ttftMs: Math.round((firstTokenAt ?? fullReplyAt) - turnStart),
          totalMs: Math.round(fullReplyAt - turnStart),
          chars: answer.length,
        });
        // Graded after the fact and patched in by id: the next question may
        // already be under way by the time the judge is done.
        const gradedTurnId = turnIdRef.current;
        if (groundednessPending && gradedTurnId) {
          setReplyGroundedness(replyId, "pending");
          fetchGroundedness(gradedTurnId)
            .then((result) => setReplyGroundedness(replyId, result))
            .catch((err) => {
              console.warn("[groundedness] grading failed:", err);
              setReplyGroundedness(replyId, "failed");
            });
        }
        clientTimingRef.current.fullReply = Math.round(fullReplyAt - turnStart);
        clientTimingRef.current.chars = answer.length;
        // Sent now rather than waiting for audio to finish: a student who
        // stops the voice, or never enabled it, would otherwise never produce
        // a row. The spoken milestones are filled in by a second post.
        if (turnIdRef.current) {
          reportTurnTimings({
            turn_id: turnIdRef.current,
            session_id: sessionIdRef.current ?? undefined,
            ttft_ms: clientTimingRef.current.ttft,
            first_sentence_ms: clientTimingRef.current.firstSentence,
            first_audio_ms: clientTimingRef.current.firstAudio,
            full_reply_ms: clientTimingRef.current.fullReply,
            answer_chars: clientTimingRef.current.chars,
          });
        }

        // The last sentence has no trailing whitespace to prove it ended, so it
        // is always still sitting in the tail here.
        const tail = unspoken.trim();
        if (tail) enqueueSpeech(tail);
        // Nothing more is coming this turn: let the player release its prebuffer.
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
    [subjectName, level, speak, cancelSpeech, endSpeech, setReplyText, setReplyMetrics, setReplyGroundedness],
  );

  // The single path from a captured question to a turn. Guarded so the mic's
  // "Send" and the silence-timeout effect can't both fire for one utterance.
  const submitQuestion = useCallback(
    (question: string) => {
      if (submittingRef.current) return;
      submittingRef.current = true;
      resetTranscript();
      void askAndSpeak(question);
    },
    [resetTranscript, askAndSpeak],
  );

  // Logs time-to-first-audio and total voice->fully-spoken duration by watching
  // the player's isPlaying flag, since speak() returns as soon as the phrase is
  // queued rather than when audio actually starts/stops.
  useEffect(() => {
    const turnStart = turnStartRef.current;
    if (turnStart === null) return;

    if (isPlaying && !firstAudioLoggedRef.current && speakQueueStartRef.current !== null) {
      firstAudioLoggedRef.current = true;
      const now = performance.now();
      clientTimingRef.current.firstAudio = Math.round(now - turnStart);
      const synthMs = now - speakQueueStartRef.current;
      const chars = Math.max(firstChunkCharsRef.current, 1);
      console.log(
        `[timing] first sentence queued -> first audio: ${synthMs.toFixed(0)}ms ` +
          `for ${firstChunkCharsRef.current} chars (${(synthMs / chars).toFixed(1)}ms/char) ` +
          `(voice -> first audio total: ${(now - turnStart).toFixed(0)}ms)`,
      );
    }

    if (!isPlaying && firstAudioLoggedRef.current && allChunksQueuedRef.current) {
      const now = performance.now();
      console.log(`[timing] voice -> fully spoken total: ${(now - turnStart).toFixed(0)}ms`);
      // Second post for the same turn_id: the audio milestones are only known
      // now, well after the text finished. The CSV keeps both rows -- analysis
      // takes the last one per turn, and a turn whose voice was cut short
      // still has its text row from earlier.
      if (turnIdRef.current) {
        reportTurnTimings({
          turn_id: turnIdRef.current,
          session_id: sessionIdRef.current ?? undefined,
          ttft_ms: clientTimingRef.current.ttft,
          first_sentence_ms: clientTimingRef.current.firstSentence,
          first_audio_ms: clientTimingRef.current.firstAudio,
          full_reply_ms: clientTimingRef.current.fullReply,
          fully_spoken_ms: Math.round(now - turnStart),
          answer_chars: clientTimingRef.current.chars,
        });
      }
      turnStartRef.current = null;
    }
  }, [isPlaying]);

  // Auto-send once the mic closes -- on the silence timeout or the mic's "Send"
  // (finishTurn). The backend decodes the whole clip after the mic closes, so
  // the transcript is only ready once `isTranscribing` clears; hold off until
  // then. A cancelled turn (cancelTurn) sets listeningHandledRef and is dropped.
  useEffect(() => {
    if (isTranscribing) return;
    if (wasListening.current && !isListening) {
      wasListening.current = false;
      if (listeningHandledRef.current) return;
      const question = collapseSpaces(`${transcript} ${interimTranscript}`);
      if (question) submitQuestion(question);
      else setStage("idle");
      return;
    }
    wasListening.current = isListening;
  }, [isListening, isTranscribing, transcript, interimTranscript, submitQuestion]);

  // The clip is being decoded: show "thinking" rather than "listening".
  useEffect(() => {
    if (isTranscribing && !listeningHandledRef.current) setStage("thinking");
  }, [isTranscribing]);

  useEffect(() => {
    if (sttError) setError(sttError);
  }, [sttError]);

  useEffect(() => {
    if (voiceError) setError("The tutor's voice is unavailable; answers will be shown but not read aloud.");
  }, [voiceError]);

  useEffect(() => {
    if (isListening) setStage("listening");
  }, [isListening]);

  const startTurn = useCallback(() => {
    setError(null);
    listeningHandledRef.current = false;
    submittingRef.current = false;
    resetTranscript();
    startListening();
  }, [resetTranscript, startListening]);

  const cancelTurn = useCallback(() => {
    listeningHandledRef.current = true;
    stopListening();
    resetTranscript();
    setStage("idle");
  }, [stopListening, resetTranscript]);

  /**
   * The mic's "Send": stop capturing now instead of waiting out the silence
   * timeout. The auto-send effect submits once the backend has decoded the clip;
   * with nothing said it just goes idle, so an accidental tap cancels cleanly.
   */
  const finishTurn = useCallback(() => {
    stopListening();
  }, [stopListening]);

  // Clears what is queued and silences the sentence already playing.
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
    isListening,
    transcript,
    interimTranscript,
    isPlaying,
    // Ready once the backend's speech-to-text model answers; the voice itself is
    // warmed by the backend at boot and never gates the mic.
    isVoiceReady: isVoiceReady && !sttLoading,
    voiceDownloadProgress: sttProgress,
    isModelWarm,
    browserSupportsSpeechRecognition: sttSupported,
    isVoiceEnabled,
    startTurn,
    cancelTurn,
    finishTurn,
    stopSpeaking,
    toggleVoice,
  };
}
