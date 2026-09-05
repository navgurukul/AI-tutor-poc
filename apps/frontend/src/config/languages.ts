// The languages offered in the tutor's language selector.
//
//  - `name`   goes to the backend as `profile.language` ("Reply in <name>.")
//             AND as the ?language= key for /api/stt and /api/tts.
//  - `speech` is a BCP-47 tag, passed to the speech-to-text engine.
//  - `native` is the label shown in the dropdown.
//
// Both halves of the speech pipeline run on the backend through sherpa-onnx,
// fully offline, keyed by `name`:
//
//   /api/stt  English -> Whisper base.en; Hindi/Marathi -> AI4Bharat
//             IndicConformer (Devanagari output).
//   /api/tts  one Piper voice per language. The voices live on the server
//             (apps/backend/models/tts/, placed by
//             scripts/package_tts_voices.py) — the browser downloads no models
//             and only plays the WAV it gets back.
//
// Adding a language: add it here, and add a voice entry to the VOICES map in
// scripts/package_tts_voices.py.
export interface TutorLanguage {
  code: string;
  name: string;
  native: string;
  speech: string;
}

export const LANGUAGES: TutorLanguage[] = [
  { code: "en", name: "English", native: "English", speech: "en-US" },
  { code: "hi", name: "Hindi", native: "हिन्दी", speech: "hi-IN" },
  { code: "mr", name: "Marathi", native: "मराठी", speech: "mr-IN" },
];

export const DEFAULT_LANGUAGE = LANGUAGES[0];

export function languageByCode(code: string | null | undefined): TutorLanguage {
  return LANGUAGES.find((l) => l.code === code) ?? DEFAULT_LANGUAGE;
}
