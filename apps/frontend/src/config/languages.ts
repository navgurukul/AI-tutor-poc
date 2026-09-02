// The languages offered in the tutor's language selector.
//
//  - `name`   goes to the backend as `profile.language` ("Reply in <name>.")
//             AND as the ?language= key for /api/stt.
//  - `speech` is a BCP-47 tag (used by the OS speechSynthesis fallback).
//  - `native` is the label shown in the dropdown.
//  - `stt`    picks the speech-to-text engine.
//  - `piper`  Piper voice files (served from public/models/) for browser TTS via
//             react-sts-hooks `usePiper`; omit to use the OS speechSynthesis
//             voice instead.
//
// Speech-to-text — every language goes through the backend /api/stt route
// (sherpa-onnx), fully offline: English -> Whisper base.en; Hindi/Marathi ->
// AI4Bharat IndicConformer (Devanagari output).
//
// Text-to-speech — browser Piper (WASM, via react-sts-hooks) for English and
// Hindi; Marathi has no Piper voice, so it falls back to the OS speechSynthesis
// voice (shows a "no offline voice" hint unless the Windows pack is installed).
export type SttEngine = { engine: "browser" } | { engine: "backend" };

export interface PiperVoice {
  /** URL to the .onnx voice model, e.g. "/models/hi_IN-priyamvada-medium.onnx". */
  model: string;
  /** URL to the matching .json voice config. */
  config: string;
  /**
   * A full sentence synthesized once at load (behind the "downloading voice"
   * state) so the first real answer skips onnxruntime-web's cold first-inference
   * cost. Use the language's own script so the phonemizer path is warmed too.
   */
  warmup: string;
}

export interface TutorLanguage {
  code: string;
  name: string;
  native: string;
  speech: string;
  stt: SttEngine;
  piper?: PiperVoice;
}

const BACKEND: SttEngine = { engine: "backend" };

export const LANGUAGES: TutorLanguage[] = [
  {
    code: "en",
    name: "English",
    native: "English",
    speech: "en-US",
    stt: BACKEND,
    piper: {
      // en_US-amy-low (16 kHz) not -medium: on a single-thread WASM CPU the
      // medium model runs ~200-300 ms per character, so a 100-char first
      // sentence was 20-30 s of synthesis. Low is ~2-3x faster for the same
      // voice. Hindi has no -low export, so it stays on medium.
      model: "/models/en_US-amy-low.onnx",
      config: "/models/en_US-amy-low.json",
      warmup: "Let's warm up the voice with a full sentence before the first answer.",
    },
  },
  {
    code: "hi",
    name: "Hindi",
    native: "हिन्दी",
    speech: "hi-IN",
    stt: BACKEND,
    piper: {
      model: "/models/hi_IN-priyamvada-medium.onnx",
      config: "/models/hi_IN-priyamvada-medium.json",
      warmup: "पहले उत्तर से पहले आवाज़ को एक पूरे वाक्य से तैयार कर लेते हैं।",
    },
  },
  { code: "mr", name: "Marathi", native: "मराठी", speech: "mr-IN", stt: BACKEND },
];

export const DEFAULT_LANGUAGE = LANGUAGES[0];

export function languageByCode(code: string | null | undefined): TutorLanguage {
  return LANGUAGES.find((l) => l.code === code) ?? DEFAULT_LANGUAGE;
}
