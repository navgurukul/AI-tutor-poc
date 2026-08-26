import { useCallback, useEffect, useRef, useState } from "react";
import { useSpeechToText, usePiper } from "react-sts-hooks";
import { askTutor } from "../services/api";
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
// entire thing is synthesized. Splitting into sentences and calling speak() per
// sentence lets Piper's own queue play the first one while later ones are still
// being synthesized, cutting time-to-first-audio down to a single sentence.
function splitIntoSpeechChunks(text: string): string[] {
  const sentences = text.match(/[^.!?]+[.!?]+(?:\s+|$)|[^.!?]+$/g) ?? [text];
  return sentences.map((s) => s.trim()).filter(Boolean);
}

export function useTutorSession({ subjectName, level, lang = "en-US" }: UseTutorSessionArgs) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [stage, setStage] = useState<TutorStage>("idle");
  const [error, setError] = useState<string | null>(null);
  const wasListening = useRef(false);
  const sessionIdRef = useRef<string | undefined>(undefined);

  // Pipeline timing: voice captured -> backend reply -> first audio -> speech done.
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
      firstAudioLoggedRef.current = false;
      allChunksQueuedRef.current = false;

      setStage("thinking");
      setMessages((prev) => [...prev, { id: nextId(), role: "user", text: question }]);
      try {
        const { sessionId, answer } = await askTutor({
          message: question,
          sessionId: sessionIdRef.current,
          profile: { subject: subjectName, level },
        });
        const backendMs = performance.now() - turnStart;
        console.log(`[timing] voice -> backend reply: ${backendMs.toFixed(0)}ms`);

        sessionIdRef.current = sessionId;
        setMessages((prev) => [...prev, { id: nextId(), role: "tutor", text: answer }]);
        setStage("speaking");

        speakQueueStartRef.current = performance.now();
        for (const chunk of splitIntoSpeechChunks(answer)) {
          await speak(chunk);
        }
        allChunksQueuedRef.current = true;
        setStage("idle");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
        setStage("error");
      }
    },
    [subjectName, level, speak]
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
        `[timing] backend reply -> first audio: ${(now - speakQueueStartRef.current).toFixed(0)}ms ` +
          `(voice -> first audio total: ${(now - turnStart).toFixed(0)}ms)`
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
