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
  /** The voice failed to load, so answers won't be read aloud. */
  voiceError: boolean;
  /** The Piper voice model is still downloading (first use only). */
  voiceLoading: boolean;
  voiceDownloadProgress: { loaded: number; total: number } | null;
}

/**
 * Text-to-speech for the tutor: browser Piper WASM (`usePiperTts`, our vendored
 * react-sts-hooks Piper with a real `stop()`), for every language.
 *
 * The voice `.onnx` named by `language.piper` is downloaded once and cached,
 * then synthesis runs on-device - no network, no OS voices. A language without
 * a `piper` block has no voice; see config/languages.ts for how to add one.
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

  return {
    speak: piper.speak,
    cancel: piper.stop,
    primeAudio: () => {},
    isSupported: !!language.piper && !piper.error,
    // Don't gate the mic on the model download — the first answer's audio just
    // waits for it; every answer after is instant (voice is cached).
    isReady: true,
    isSpeaking: piper.isPlaying,
    voiceError: !!piper.error,
    voiceLoading: piper.isLoading,
    voiceDownloadProgress: piper.downloadProgress ?? null,
  };
}
