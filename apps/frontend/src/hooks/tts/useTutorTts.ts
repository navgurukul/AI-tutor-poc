import { useBackendTts } from "./useBackendTts";
import type { TutorLanguage } from "../../config/languages";

export interface TutorTtsApi {
  speak: (text: string) => void;
  cancel: () => void;
  /** Resume the audio pipeline from a user gesture. No-op here. */
  primeAudio: () => void;
  isSupported: boolean;
  isReady: boolean;
  isSpeaking: boolean;
  /** The voice isn't available, so answers won't be read aloud. */
  voiceError: boolean;
}

/**
 * Text-to-speech for the tutor: the backend's /api/tts, which runs sherpa-onnx
 * with one Piper voice per language (see apps/backend/app/services/tts.py).
 *
 * The browser only plays the WAV it receives — the same engine and voices that
 * used to run in a WASM worker here, but ~12-20x faster on native CPU, and with
 * nothing for the client to download.
 */
export function useTutorTts(language: TutorLanguage): TutorTtsApi {
  const tts = useBackendTts(language.name);

  return {
    speak: tts.speak,
    cancel: tts.stop,
    primeAudio: () => {},
    isSupported: !tts.error,
    // Don't gate the mic on the voice: the backend warms every installed voice
    // at boot, and a missing one only costs the audio, not the answer.
    isReady: true,
    isSpeaking: tts.isPlaying,
    voiceError: !!tts.error,
  };
}
