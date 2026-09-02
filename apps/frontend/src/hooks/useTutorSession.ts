import { useCallback, useEffect, useRef, useState } from "react";
import { askTutorStream, warmupTutor } from "../services/api";
import { useTutorTts } from "./tts/useTutorTts";
import { useTutorSpeechToText } from "./stt/useTutorSpeechToText";
import type { TutorLanguage } from "../config/languages";
import type { ChatMessage } from "../types";

export type TutorStage = "idle" | "listening" | "thinking" | "speaking" | "error";

interface UseTutorSessionArgs {
  subjectName: string;
  level: string;
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

// The reply is spoken one sentence at a time as the model decodes — the first
// sentence starts playing while the rest is still being written, and the Piper
// queue plays them back-to-back with no gaps. Sentences shorter than this are
// merged with the next one before being spoken, so a lone two-word opener
// doesn't play out in a second and leave dead air while the LLM writes more.
const MIN_SPEECH_CHARS = 60;

// ...except the *first* chunk of a turn, which is queued as soon as it clears
// this lower bar — Piper synth time scales with length, so starting on a ~30-
// char opener is audible much sooner. Not 1: a trivially short opener ("ये है:")
// plays out in a blink and leaves dead air while the next sentence synthesizes.
const FIRST_CHUNK_MIN_CHARS = 30;

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
): { sentences: string[]; rest: string } {
  const sentences: string[] = [];
  // A `.` right after a digit is a list marker ("1. ") or a decimal, not a
  // sentence end — the negative lookbehind keeps "ये है: 1." from being spoken
  // as its own fragment. The danda (। ॥) is always a sentence end.
  const boundary = /(?:(?<!\d)[.!?…]+["')\]]*(?=\s)|[।॥]+)/g;
  let rest = buffer;
  let searchFrom = 0;

  for (;;) {
    boundary.lastIndex = searchFrom;
    const match = boundary.exec(rest);
    if (!match) break;

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

export function useTutorSession({ subjectName, level, language }: UseTutorSessionArgs) {
  const langName = language.name;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [stage, setStage] = useState<TutorStage>("idle");
  const [error, setError] = useState<string | null>(null);
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
    cancel: cancelSpeech,
    primeAudio,
    isSupported: isSpeechSupported,
    isReady: isVoiceReady,
    isSpeaking: isPlaying,
    voiceMissing,
    voiceLoading,
    voiceDownloadProgress,
  } = useTutorTts(language);

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

  // Warm-load the LLM the moment the session mounts, and again whenever the
  // language changes. Ollama otherwise loads the weights (and, on a language
  // switch, re-processes the whole new system prompt) lazily on the first
  // question. Re-gating `isModelWarm` here keeps the mic disabled until Ollama
  // has the new-language prompt prefix cached, so the first turn after a switch
  // isn't the one that pays ~10-16s.
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const startedAt = performance.now();
    setIsModelWarm(false);
    void warmupTutor({ subject: subjectName, level, language: langName }, controller.signal)
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
  }, [subjectName, level, langName]);

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
    setStage("idle");
  }, [language.code, resetTranscript, cancelSpeech]);

  const askAndSpeak = useCallback(
    async (question: string) => {
      const turnStart = performance.now();
      turnStartRef.current = turnStart;
      speakQueueStartRef.current = null;
      firstAudioLoggedRef.current = false;
      allChunksQueuedRef.current = false;
      speechStoppedRef.current = false;

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
      let firstTokenAt: number | null = null;

      const enqueueSpeech = (text: string) => {
        if (!voiceEnabledRef.current || speechStoppedRef.current) return;
        const spoken = stripForSpeech(text);
        if (!spoken) return;
        if (speakQueueStartRef.current === null) {
          speakQueueStartRef.current = performance.now();
          console.log(
            `[timing] voice -> first sentence queued: ${(speakQueueStartRef.current - turnStart).toFixed(0)}ms ` +
              `(${spoken.length} chars: "${spoken.slice(0, 60)}${spoken.length > 60 ? "…" : ""}")`,
          );
        }
        // The speech queue plays phrases in order, gaplessly.
        speak(spoken);
      };

      try {
        await askTutorStream(
          {
            message: question,
            sessionId: sessionIdRef.current,
            profile: { subject: subjectName, level, language: langName },
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

              // First chunk: break at the first sentence boundary, however
              // short, so audio starts as soon as possible. After that, hold out
              // for MIN_SPEECH_CHARS so the voice doesn't stutter phrase-by-phrase.
              const minChars =
                speakQueueStartRef.current === null
                  ? FIRST_CHUNK_MIN_CHARS
                  : MIN_SPEECH_CHARS;
              const { sentences, rest } = drainSentences(unspoken, minChars);
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
    [subjectName, level, langName, speak, cancelSpeech, setReplyText],
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
    }

    if (!isPlaying && firstAudioLoggedRef.current && allChunksQueuedRef.current) {
      const now = performance.now();
      console.log(`[timing] voice -> fully spoken total: ${(now - turnStart).toFixed(0)}ms`);
      turnStartRef.current = null;
    }
  }, [isPlaying]);

  // Auto-send once the mic closes — covers both the silence timeout and a manual
  // "Send" (finishTurn), which just close the mic. The live transcript is shown
  // in the chat as it is spoken; nothing else is typed. For a batch STT engine
  // (IndicConformer) the transcript isn't ready until `isTranscribing` clears,
  // so hold off submitting until then.
  useEffect(() => {
    if (isTranscribing) return;

    if (wasListening.current && !isListening) {
      wasListening.current = false;
      if (cancelledRef.current) {
        cancelledRef.current = false;
        resetTranscript();
        setStage("idle");
        return;
      }
      const question = collapseSpaces(`${transcript} ${interimTranscript}`);
      if (question) submitQuestion(question);
      else setStage("idle");
      return;
    }

    wasListening.current = isListening;
  }, [
    isListening,
    isTranscribing,
    transcript,
    interimTranscript,
    submitQuestion,
    resetTranscript,
  ]);

  // Show the "working on it" state during a batch transcribe, and disable the
  // mic — unless the user just cancelled, in which case stay idle.
  useEffect(() => {
    if (isTranscribing && !cancelledRef.current) setStage("thinking");
  }, [isTranscribing]);

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
    isListening,
    isTranscribing,
    transcript,
    interimTranscript,
    isPlaying,
    isVoiceReady,
    isSpeechSupported,
    voiceMissing,
    voiceLoading,
    voiceDownloadProgress,
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
