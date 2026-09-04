// The languages offered in the tutor's language selector.
//
//  - `name`   goes to the backend as `profile.language` ("Reply in <name>.")
//             AND as the ?language= key for /api/stt.
//  - `speech` is a BCP-47 tag, passed to the speech-to-text engine.
//  - `native` is the label shown in the dropdown.
//  - `piper`  Piper voice files, served from public/models/, for browser TTS.
//
// Speech-to-text — every language goes through the backend /api/stt route
// (sherpa-onnx), fully offline: English -> Whisper base.en; Hindi/Marathi ->
// AI4Bharat IndicConformer (Devanagari output).
//
// Text-to-speech — browser Piper (WASM) for every language, fully offline. Each
// voice is one .onnx + .json in public/models/. Adding a language means adding
// its voice files and a `piper` block here; nothing else changes.
// Voices come from https://huggingface.co/rhasspy/piper-voices (auditionable at
// https://rhasspy.github.io/piper-samples/).
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
  piper?: PiperVoice;
}

export const LANGUAGES: TutorLanguage[] = [
  {
    code: "en",
    name: "English",
    native: "English",
    speech: "en-US",
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
    piper: {
      model: "/models/hi_IN-priyamvada-medium.onnx",
      config: "/models/hi_IN-priyamvada-medium.json",
      warmup: "पहले उत्तर से पहले आवाज़ को एक पूरे वाक्य से तैयार कर लेते हैं।",
    },
  },
  {
    code: "mr",
    name: "Marathi",
    native: "मराठी",
    speech: "mr-IN",
    piper: {
      // mr_IN-google-medium is a 9-speaker model; the worker sends sid 0 when a
      // model has a speaker_id_map, which is mrt_01523 - the voice on the Piper
      // samples page. Like Hindi, there's no -low export, so it stays on medium.
      model: "/models/mr_IN-google-medium.onnx",
      config: "/models/mr_IN-google-medium.json",
      warmup: "पहिल्या उत्तराआधी संपूर्ण वाक्याने आवाज तयार करून घेऊ.",
    },
  },
];

export const DEFAULT_LANGUAGE = LANGUAGES[0];

export function languageByCode(code: string | null | undefined): TutorLanguage {
  return LANGUAGES.find((l) => l.code === code) ?? DEFAULT_LANGUAGE;
}
