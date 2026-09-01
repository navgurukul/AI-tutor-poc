import { useSpeechSynthesis } from "../useSpeechSynthesis";
import { useBackendTts } from "./useBackendTts";
import type { TutorLanguage } from "../../config/languages";

export interface TutorTtsApi {
  speak: (text: string) => void;
  cancel: () => void;
  /** Resume the audio pipeline from a user gesture. No-op for the OS voice. */
  primeAudio: () => void;
  isSupported: boolean;
  isReady: boolean;
  isSpeaking: boolean;
  voiceMissing: boolean;
  /** Only meaningful for the backend engine — the voice model is loading. */
  voiceLoading: boolean;
  voiceDownloadProgress: { loaded: number; total: number } | null;
}

/**
 * Picks the text-to-speech engine for the current language:
 *   `tts: "backend"` -> the backend `/api/tts` route (sherpa-onnx + Piper voice).
 *   otherwise        -> the OS `speechSynthesis` voice.
 * Both hooks are mounted every render; the inactive one stays dormant.
 */
export function useTutorTts(language: TutorLanguage): TutorTtsApi {
  const useBackend = language.tts === "backend";

  const browser = useSpeechSynthesis(language.speech);
  const backend = useBackendTts(useBackend);

  if (useBackend) return backend;
  return {
    ...browser,
    primeAudio: () => {},
    voiceLoading: false,
    voiceDownloadProgress: null,
  };
}
