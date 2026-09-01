// The languages offered in the tutor's language selector.
//
//  - `name`   goes to the backend as `profile.language` ("Reply in <name>.").
//  - `speech` is the BCP-47 tag handed to the Web Speech API for recognition.
//  - `native` is the label shown in the dropdown.
//  - `stt`    picks the speech-to-text engine (see below).
//
// Speech-to-text engine is per-language:
//
//   - "browser": the Chrome/Edge Web Speech API. On-device for English, so it
//               works with or without network.
//   - "indic":  the backend's /api/stt route running sherpa-onnx + AI4Bharat's
//               IndicConformer. This model outputs Devanagari, so it's used for
//               Hindi and Marathi (Gujarati/Kannada would need per-language
//               models — see apps/backend/README.md).
//
// Piper's voice is English-only, so a non-English answer is still read aloud
// with the English voice.
export type SttEngine = { engine: "browser" } | { engine: "indic" };

export interface TutorLanguage {
  code: string;
  name: string;
  native: string;
  speech: string;
  stt: SttEngine;
}

const INDIC: SttEngine = { engine: "indic" };

export const LANGUAGES: TutorLanguage[] = [
  { code: "en", name: "English", native: "English", speech: "en-US", stt: { engine: "browser" } },
  { code: "hi", name: "Hindi", native: "हिन्दी", speech: "hi-IN", stt: INDIC },
  { code: "mr", name: "Marathi", native: "मराठी", speech: "mr-IN", stt: INDIC },
];

export const DEFAULT_LANGUAGE = LANGUAGES[0];

export function languageByCode(code: string | null | undefined): TutorLanguage {
  return LANGUAGES.find((l) => l.code === code) ?? DEFAULT_LANGUAGE;
}
