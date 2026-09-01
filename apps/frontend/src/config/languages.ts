// The languages offered in the tutor's language selector.
//
//  - `name`   goes to the backend as `profile.language` ("Reply in <name>.").
//  - `speech` is the BCP-47 tag handed to the Web Speech API.
//  - `native` is the label shown in the dropdown.
//  - `stt`    picks the speech-to-text engine.
//  - `tts`    "backend" routes speech output through /api/tts (sherpa-onnx +
//             a Piper voice); omit to use the OS speechSynthesis voice.
//
// Speech-to-text engine is per-language:
//   - "browser": the Chrome/Edge Web Speech API. On-device for English.
//   - "indic":  the backend /api/stt route (sherpa-onnx + AI4Bharat
//               IndicConformer). Devanagari output — Hindi and Marathi.
//
// Text-to-speech:
//   - English -> OS speechSynthesis (instant, no model).
//   - Hindi   -> backend Piper `hi_IN-priyamvada` (female), offline.
//   - Marathi -> OS speechSynthesis (Piper has no Marathi voice); shows the
//               "no offline voice" hint unless the OS pack is installed.
export type SttEngine = { engine: "browser" } | { engine: "indic" };

export interface TutorLanguage {
  code: string;
  name: string;
  native: string;
  speech: string;
  stt: SttEngine;
  tts?: "backend";
}

const INDIC: SttEngine = { engine: "indic" };

export const LANGUAGES: TutorLanguage[] = [
  { code: "en", name: "English", native: "English", speech: "en-US", stt: { engine: "browser" } },
  { code: "hi", name: "Hindi", native: "हिन्दी", speech: "hi-IN", stt: INDIC, tts: "backend" },
  { code: "mr", name: "Marathi", native: "मराठी", speech: "mr-IN", stt: INDIC },
];

export const DEFAULT_LANGUAGE = LANGUAGES[0];

export function languageByCode(code: string | null | undefined): TutorLanguage {
  return LANGUAGES.find((l) => l.code === code) ?? DEFAULT_LANGUAGE;
}
