import { useCallback, useEffect, useRef, useState } from "react";
import { useSpeechToText, usePiper } from "react-sts-hooks";
import { askTutor } from "../services/api";
import { VOICE_MODEL_URL, VOICE_CONFIG_URL } from "../config/voice";
import type { ChatMessage } from "../types";

export type TutorStage = "idle" | "listening" | "thinking" | "speaking" | "error";

interface UseTutorSessionArgs {
  classId: string;
  subjectId: string;
  lang?: string;
}

let messageId = 0;
const nextId = () => `msg-${++messageId}`;

export function useTutorSession({ classId, subjectId, lang = "en-US" }: UseTutorSessionArgs) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [stage, setStage] = useState<TutorStage>("idle");
  const [error, setError] = useState<string | null>(null);
  const wasListening = useRef(false);

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
      setStage("thinking");
      setMessages((prev) => [...prev, { id: nextId(), role: "user", text: question }]);
      try {
        const { answer } = await askTutor({ classId, subjectId, question });
        setMessages((prev) => [...prev, { id: nextId(), role: "tutor", text: answer }]);
        setStage("speaking");
        await speak(answer);
        setStage("idle");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
        setStage("error");
      }
    },
    [classId, subjectId, speak]
  );

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
