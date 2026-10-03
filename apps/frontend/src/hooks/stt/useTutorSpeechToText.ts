import type { TutorLanguage } from "../../config/languages";
import type { TutorStt } from "./types";
import { useIndicSpeechToText } from "./useIndicSpeechToText";

/**
 * Speech-to-text for the tutor: every language goes to the backend /api/stt
 * route (sherpa-onnx), fully offline — Whisper base.en for English,
 * AI4Bharat IndicConformer for Hindi/Marathi.
 */
export function useTutorSpeechToText(language: TutorLanguage): TutorStt {
  return useIndicSpeechToText({
    active: true,
    speechLang: language.speech,
    language: language.name,
  });
}
