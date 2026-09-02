import type { TutorLanguage } from "../../config/languages";
import type { TutorStt } from "./types";
import { useBrowserSpeechToText } from "./useBrowserSpeechToText";
import { useIndicSpeechToText } from "./useIndicSpeechToText";

/**
 * Picks the speech-to-text engine for the current language and hands its output
 * straight through. Every engine hook is mounted every render (rules of hooks);
 * the `active` flag keeps the unselected one dormant — no mic, no backend calls.
 *
 *   All languages -> backend /api/stt (sherpa-onnx): Moonshine for English,
 *                    IndicConformer for Hindi/Marathi. Fully offline.
 *   "browser"     -> the Chrome/Edge Web Speech API. Kept as an option; no
 *                    language routes here today.
 */
export function useTutorSpeechToText(language: TutorLanguage): TutorStt {
  const engine = language.stt.engine;

  const browser = useBrowserSpeechToText({
    active: engine === "browser",
    speechLang: language.speech,
    language: language.name,
  });
  const backend = useIndicSpeechToText({
    active: engine === "backend",
    speechLang: language.speech,
    language: language.name,
  });

  return engine === "browser" ? browser : backend;
}
