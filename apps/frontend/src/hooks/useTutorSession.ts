import { useCallback, useEffect, useRef, useState } from "react";
import { useSpeechToText, usePiper } from "react-sts-hooks";
import { askTutorStream, warmupTutor } from "../services/api";
import { VOICE_MODEL_URL, VOICE_CONFIG_URL } from "../config/voice";
import { allowSpeech, installSpeechInterceptor, stopSpeech } from "../utils/stopSpeech";
import type { ChatMessage } from "../types";

export type TutorStage = "idle" | "listening" | "thinking" | "speaking" | "error";

interface UseTutorSessionArgs {
  subjectName: string;
  level: string;
  lang?: string;
}

installSpeechInterceptor();

// Unique per message and stable across HMR reloads. A module-level counter
// resets on hot-reload while the `messages` state survives, so ids collide and a
// streamed reply lands on an earlier bubble instead of its own.
const nextId = (): string =>
  globalThis.crypto?.randomUUID?.() ??
  `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

// STT builds `transcript` as `prev + " " + chunk`, so it carries a leading space
// and can gather doubles where an interim tail is appended.
const collapseSpaces = (s: string) => s.replace(/\s+/g, " ").trim();

// Piper synthesizes each speak() call as one WASM pass before any of it plays,
// so the reply is handed over one sentence at a time as the backend streams
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

export function useTutorSession({ subjectName, level, lang = "en-US" }: UseTutorSessionArgs) {
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
  const speakQueueStartRef = useRef<number | null>(null);
  const firstAudioLoggedRef = useRef(false);
  const allChunksQueuedRef = useRef(false);

  const {
    startListening,
    stopListening,
    transcript,
    interimTranscript,
    isListening,
    resetTranscript,
    browserSupportsSpeechRecognition,
    error: sttError,
  } = useSpeechToText({ lang, continuous: true, silenceTimeout: 1000 });

  const {
    speak,
    resetTTS,
    isReady: isVoiceReady,
    isLoading: isVoiceLoading,
    isPlaying,
    downloadProgress,
    error: ttsError,
  } = usePiper({
    voiceModelUrl: VOICE_MODEL_URL,
    voiceConfigUrl: VOICE_CONFIG_URL,
  });

  // The id of the tutor bubble for the turn in flight, so the streaming update
  // always targets the right message.
  const replyIdRef = useRef<string | null>(null);

  const setReplyText = useCallback((text: string) => {
    const id = replyIdRef.current;
    if (!id) return;
    setMessages((prev) => {
      const index = prev.findIndex((m) => m.id === id);
      if (index === -1) return [...prev, { id, role: "tutor", text }];
      const next = [...prev];
      next[index] = { ...next[index], text };
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
      allChunksQueuedRef.current = false;
      speechStoppedRef.current = false;

      // Clear anything still queued in Piper and silence a sentence still
      // playing from a previous turn; suppress until this turn starts speaking.
      resetTTS();
      stopSpeech();

      setStage("thinking");
      setMessages((prev) => [...prev, { id: nextId(), role: "user", text: question }]);

      const replyId = nextId();
      replyIdRef.current = replyId;
      const controller = new AbortController();
      streamAbortRef.current = controller;

      let answer = "";
      let unspoken = "";
      let firstTokenAt: number | null = null;
      // speak() resolves when the phrase is queued, not when it finishes
      // playing; chaining keeps sentences in order without blocking the reader.
      let speechChain: Promise<unknown> = Promise.resolve();

      const enqueueSpeech = (text: string) => {
        if (!voiceEnabledRef.current || speechStoppedRef.current) return;
        if (speakQueueStartRef.current === null) {
          speakQueueStartRef.current = performance.now();
          // Re-arm playback only once the first sentence is actually ready, so a
          // previous turn's Stop stays in force right up to this moment.
          allowSpeech();
          console.log(
            `[timing] voice -> first sentence queued: ${(speakQueueStartRef.current - turnStart).toFixed(0)}ms ` +
              `(${text.length} chars: "${text.slice(0, 60)}${text.length > 60 ? "…" : ""}")`,
          );
        }
        speechChain = speechChain.then(() => speak(text)).catch(() => undefined);
      };

      try {
        await askTutorStream(
          {
            message: question,
            sessionId: sessionIdRef.current,
            profile: { subject: subjectName, level },
          },
          {
            onStart: (sessionId) => {
              sessionIdRef.current = sessionId;
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

              const { sentences, rest } = drainSentences(unspoken);
              unspoken = rest;
              for (const sentence of sentences) enqueueSpeech(sentence);
            },
            onDone: ({ sessionId, answer: finalAnswer }) => {
              sessionIdRef.current = sessionId;
              // The server's reply is the same text, trimmed; prefer it so the
              // bubble doesn't keep stray leading/trailing whitespace.
              answer = finalAnswer || answer;
              setReplyText(answer);
            },
          },
          controller.signal,
        );

        console.log(
          `[timing] voice -> full reply: ${(performance.now() - turnStart).toFixed(0)}ms`,
        );

        // The last sentence has no trailing whitespace to prove it ended, so it
        // is always still sitting in the tail here.
        const tail = unspoken.trim();
        if (tail) enqueueSpeech(tail);

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
    [subjectName, level, speak, resetTTS, setReplyText],
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
  // Piper's isPlaying flag, since speak() resolves as soon as the phrase is
  // queued rather than when audio actually starts/stops.
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
    }

    if (!isPlaying && firstAudioLoggedRef.current && allChunksQueuedRef.current) {
      const now = performance.now();
      console.log(`[timing] voice -> fully spoken total: ${(now - turnStart).toFixed(0)}ms`);
      turnStartRef.current = null;
    }
  }, [isPlaying]);

  // Auto-send once the mic goes quiet for silenceTimeout and stops on its own.
  // A manual "Send" (finishTurn) sets listeningHandledRef and submits there.
  useEffect(() => {
    if (wasListening.current && !isListening && !listeningHandledRef.current) {
      const question = collapseSpaces(`${transcript} ${interimTranscript}`);
      if (question) submitQuestion(question);
    }
    wasListening.current = isListening;
  }, [isListening, transcript, interimTranscript, submitQuestion]);

  useEffect(() => {
    if (sttError) setError(sttError);
    if (ttsError) setError(ttsError);
  }, [sttError, ttsError]);

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
   * The mic's "Send": stop capturing and submit whatever was said *now*, instead
   * of waiting out the silence timeout. With nothing said yet it just goes idle,
   * so an accidental tap still cancels cleanly.
   */
  const finishTurn = useCallback(() => {
    const question = collapseSpaces(`${transcript} ${interimTranscript}`);
    listeningHandledRef.current = true;
    stopListening();
    if (question) {
      submitQuestion(question);
    } else {
      resetTranscript();
      setStage("idle");
    }
  }, [transcript, interimTranscript, stopListening, resetTranscript, submitQuestion]);

  // resetTTS() clears what is queued; stopSpeech() silences the sentence already
  // playing and blocks any chunk still mid-synthesis. Both are needed to stop.
  const silenceSpeech = useCallback(() => {
    resetTTS();
    stopSpeech();
    // Drop the pending timing measurement — this turn never finished speaking.
    turnStartRef.current = null;
  }, [resetTTS]);

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
    isVoiceReady,
    isVoiceLoading,
    voiceDownloadProgress: downloadProgress,
    isModelWarm,
    browserSupportsSpeechRecognition,
    isVoiceEnabled,
    startTurn,
    cancelTurn,
    finishTurn,
    stopSpeaking,
    toggleVoice,
  };
}
