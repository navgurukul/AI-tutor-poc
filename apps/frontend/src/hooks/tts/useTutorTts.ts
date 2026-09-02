import { useSpeechSynthesis } from "../useSpeechSynthesis";
import { usePiperTts } from "./usePiperTts";
import type { TutorLanguage } from "../../config/languages";

export interface TutorTtsApi {
  speak: (text: string) => void;
  cancel: () => void;
  /** Resume the audio pipeline from a user gesture. No-op here. */
  primeAudio: () => void;
  isSupported: boolean;
  isReady: boolean;
  isSpeaking: boolean;
  voiceMissing: boolean;
  /** The Piper voice model is still downloading (first use only). */
  voiceLoading: boolean;
  voiceDownloadProgress: { loaded: number; total: number } | null;
}

/**
 * Picks the text-to-speech engine for the current language:
 *   Has a `piper` voice (English, Hindi) -> browser Piper WASM (`usePiperTts`,
 *     our vendored react-sts-hooks Piper with a real `stop()`). The voice
 *     `.onnx` is downloaded once and cached, then synthesis runs on-device.
 *   Otherwise (Marathi) -> the OS `speechSynthesis` voice.
 * Both hooks are mounted every render; the inactive one stays dormant
 * (`usePiperTts(null)` loads nothing).
 */
export function useTutorTts(language: TutorLanguage): TutorTtsApi {
  const piper = usePiperTts(
    language.piper
      ? {
          voiceModelUrl: language.piper.model,
          voiceConfigUrl: language.piper.config,
          warmupText: language.piper.warmup,
        }
      : null,
  );
  const browser = useSpeechSynthesis(language.speech);

  if (language.piper) {
    return {
      speak: piper.speak,
      cancel: piper.stop,
      primeAudio: () => {},
      isSupported: !piper.error,
      // Don't gate the mic on the model download — the first answer's audio just
      // waits for it; every answer after is instant (voice is cached).
      isReady: true,
      isSpeaking: piper.isPlaying,
      voiceMissing: !!piper.error,
      voiceLoading: piper.isLoading,
      voiceDownloadProgress: piper.downloadProgress ?? null,
    };
  }

  return {
    ...browser,
    primeAudio: () => {},
    voiceLoading: false,
    voiceDownloadProgress: null,
  };
}
