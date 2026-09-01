import type { TutorLanguage } from "../../config/languages";
import type { TutorStt } from "./types";
import { useBrowserSpeechToText } from "./useBrowserSpeechToText";
import { useIndicSpeechToText } from "./useIndicSpeechToText";

/**
 * Picks the speech-to-text engine for the current language and hands its output
 * straight through. Every engine hook is mounted every render (rules of hooks);
 * the `active` flag keeps the unselected one dormant — no mic, no backend calls.
 *
 *   English                         -> browser Web Speech API (on-device)
 *   Hindi/Gujarati/Kannada/Marathi   -> backend /api/stt (IndicConformer, offline)
 */
export function useTutorSpeechToText(language: TutorLanguage): TutorStt {
  const engine = language.stt.engine;

  const browser = useBrowserSpeechToText({
    active: engine === "browser",
    speechLang: language.speech,
  });
  const indic = useIndicSpeechToText({
    active: engine === "indic",
    speechLang: language.speech,
  });

  return engine === "indic" ? indic : browser;
}
