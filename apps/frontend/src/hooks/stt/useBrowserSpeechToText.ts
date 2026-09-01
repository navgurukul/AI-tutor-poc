import { useEffect } from "react";
import { useSpeechToText } from "react-sts-hooks";
import type { EngineHookArgs, TutorStt } from "./types";

/**
 * The Chrome/Edge Web Speech API, wrapped to the common `TutorStt` shape.
 * On-device and instant for English; for other locales the browser streams
 * audio to Google, so `languages.ts` only routes English here (Hindi goes to
 * the offline IndicConformer engine).
 *
 * There's no model to download, so `isLoading` is always false and `progress`
 * is always null. `isTranscribing` is always false too — results are final as
 * they arrive.
 */
export function useBrowserSpeechToText({ active, speechLang }: EngineHookArgs): TutorStt {
  const {
    startListening,
    stopListening,
    transcript,
    interimTranscript,
    isListening,
    resetTranscript,
    browserSupportsSpeechRecognition,
    error,
  } = useSpeechToText({ lang: speechLang, continuous: true, silenceTimeout: 1000 });

  // If the language switches away from this engine mid-listen, close the mic.
  useEffect(() => {
    if (!active && isListening) stopListening();
  }, [active, isListening, stopListening]);

  return {
    startListening,
    stopListening,
    resetTranscript,
    transcript,
    interimTranscript,
    isListening,
    isTranscribing: false,
    supported: browserSupportsSpeechRecognition,
    isLoading: false,
    progress: null,
    error: error ?? null,
  };
}
