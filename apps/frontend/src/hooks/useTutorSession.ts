import { useCallback, useEffect, useRef, useState } from "react";
import { useSpeechToText, usePiper } from "react-sts-hooks";
import { askTutorStream } from "../services/api";
import { VOICE_MODEL_URL, VOICE_CONFIG_URL } from "../config/voice";
import type { ChatMessage } from "../types";

export type TutorStage = "idle" | "listening" | "thinking" | "speaking" | "error";

interface UseTutorSessionArgs {
  subjectName: string;
  level: string;
  lang?: string;
}

let messageId = 0;
const nextId = () => `msg-${++messageId}`;

// Piper synthesizes each speak() call as one WASM pass before any of it plays,
// so speaking a whole multi-sentence reply in one call means silence until the
// entire thing is synthesized. Sentences are therefore handed to Piper one at a
// time, and — since the backend streams tokens — the first one is spoken while
// the model is still decoding the rest of the answer.
//
// Too small a fragment isn't worth its own synthesis pass (and reads as a
// stutter), so short ones are merged into the sentence that follows.
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
  const wasListening = useRef(false);
  const sessionIdRef = useRef<string | undefined>(undefined);

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
  } = useSpeechToText({ lang, continuous: true, silenceTimeout: 1500 });

  const {
    speak,
    isReady: isVoiceReady,
    isLoading: isVoiceLoading,
    isPlaying,
    downloadProgress,
    error: ttsError,
  } = usePiper({
    voiceModelUrl: VOICE_MODEL_URL,
    voiceConfigUrl: VOICE_CONFIG_URL,
  });

  const askAndSpeak = useCallback(
    async (question: string) => {
      const turnStart = performance.now();
      turnStartRef.current = turnStart;
      speakQueueStartRef.current = null;
      firstAudioLoggedRef.current = false;
      allChunksQueuedRef.current = false;

      setStage("thinking");
      setMessages((prev) => [...prev, { id: nextId(), role: "user", text: question }]);

      const replyId = nextId();

      let answer = "";
      let unspoken = "";
      let firstTokenAt: number | null = null;
      // speak() resolves when the text is queued, not when it finishes playing,
      // but chaining still keeps sentences in order without blocking the reader.
      let speechChain: Promise<unknown> = Promise.resolve();

      const enqueueSpeech = (text: string) => {
        if (speakQueueStartRef.current === null) {
          speakQueueStartRef.current = performance.now();
          console.log(
            `[timing] voice -> first sentence queued: ${(speakQueueStartRef.current - turnStart).toFixed(0)}ms`,
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

              // Render the partial answer as it decodes.
              const text = answer;
              setMessages((prev) => {
                const index = prev.findIndex((m) => m.id === replyId);
                if (index === -1) return [...prev, { id: replyId, role: "tutor", text }];
                const next = [...prev];
                next[index] = { ...next[index], text };
                return next;
              });

              const { sentences, rest } = drainSentences(unspoken);
              unspoken = rest;
              for (const sentence of sentences) enqueueSpeech(sentence);
            },
            onDone: ({ sessionId, answer: finalAnswer }) => {
              sessionIdRef.current = sessionId;
              // The server's reply is the same text, trimmed; prefer it so the
              // bubble doesn't keep stray leading/trailing whitespace.
              answer = finalAnswer || answer;
              const text = answer;
              setMessages((prev) => {
                const index = prev.findIndex((m) => m.id === replyId);
                if (index === -1) return [...prev, { id: replyId, role: "tutor", text }];
                const next = [...prev];
                next[index] = { ...next[index], text };
                return next;
              });
            },
          },
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
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
        setStage("error");
        turnStartRef.current = null;
      }
    },
    [subjectName, level, speak],
  );

  // Logs time-to-first-audio and total voice->fully-spoken duration by watching
  // Piper's isPlaying flag, since speak() itself resolves as soon as text is
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

  // Auto-send once the mic stops listening and picked up a final transcript.
  useEffect(() => {
    if (wasListening.current && !isListening && transcript.trim()) {
      const question = transcript.trim();
      resetTranscript();
      void askAndSpeak(question);
    }
    wasListening.current = isListening;
  }, [isListening, transcript, resetTranscript, askAndSpeak]);

  useEffect(() => {
    if (sttError) setError(sttError);
    if (ttsError) setError(ttsError);
  }, [sttError, ttsError]);

  useEffect(() => {
    if (isListening) setStage("listening");
  }, [isListening]);

  const startTurn = useCallback(() => {
    setError(null);
    resetTranscript();
    startListening();
  }, [resetTranscript, startListening]);

  const cancelTurn = useCallback(() => {
    stopListening();
    resetTranscript();
    setStage("idle");
  }, [stopListening, resetTranscript]);

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
    browserSupportsSpeechRecognition,
    startTurn,
    cancelTurn,
  };
}
