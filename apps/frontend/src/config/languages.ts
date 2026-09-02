// The languages offered in the tutor's language selector.
//
//  - `name`   goes to the backend as `profile.language` ("Reply in <name>.")
//             AND as the ?language= key for /api/stt and /api/tts.
//  - `speech` is a BCP-47 tag (kept for any browser speech APIs).
//  - `native` is the label shown in the dropdown.
//  - `stt`    picks the speech-to-text engine.
//  - `tts`    "backend" routes speech output through /api/tts (sherpa-onnx +
//             a Piper voice); omit to use the OS speechSynthesis voice.
//
// Speech-to-text — every language now goes through the backend /api/stt route
// (sherpa-onnx), so it's fully offline:
//   - "backend": English -> Moonshine (tiny int8); Hindi/Marathi -> AI4Bharat
//                IndicConformer (Devanagari output).
//   - "browser": the Chrome/Edge Web Speech API. Kept as an option; not used.
//
// Text-to-speech:
//   - English -> OS speechSynthesis (instant, no model).
//   - Hindi   -> backend Piper `hi_IN-priyamvada` (female), offline.
//   - Marathi -> OS speechSynthesis (Piper has no Marathi voice); shows the
//               "no offline voice" hint unless the OS pack is installed.
export type SttEngine = { engine: "browser" } | { engine: "backend" };

export interface TutorLanguage {
  code: string;
  name: string;
  native: string;
  speech: string;
  stt: SttEngine;
  tts?: "backend";
}

const BACKEND: SttEngine = { engine: "backend" };

export const LANGUAGES: TutorLanguage[] = [
  { code: "en", name: "English", native: "English", speech: "en-US", stt: BACKEND },
  { code: "hi", name: "Hindi", native: "हिन्दी", speech: "hi-IN", stt: BACKEND, tts: "backend" },
  { code: "mr", name: "Marathi", native: "मराठी", speech: "mr-IN", stt: BACKEND },
];

export const DEFAULT_LANGUAGE = LANGUAGES[0];

export function languageByCode(code: string | null | undefined): TutorLanguage {
  return LANGUAGES.find((l) => l.code === code) ?? DEFAULT_LANGUAGE;
}
