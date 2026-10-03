// The single speech-to-text surface the rest of the app depends on. Every
// engine (browser Web Speech, backend IndicConformer, ...future) is a hook that returns
// exactly this shape, so `useTutorSession` and the UI never branch on which
// engine is active — the router hook (`useTutorSpeechToText`) picks one and
// hands its output straight through.

export interface SttProgress {
  loaded: number;
  total: number;
}

export interface TutorStt {
  /** Begin capturing from the mic. No-op if the engine isn't ready. */
  startListening: () => void;
  /**
   * Stop capturing. For streaming engines the transcript is already final; for
   * batch engines (IndicConformer) this is what kicks off decoding — watch
   * `isTranscribing` for that.
   */
  stopListening: () => void;
  /** Clear `transcript` / `interimTranscript` before the next utterance. */
  resetTranscript: () => void;

  /** Settled text so far. */
  transcript: string;
  /** Best-guess tail not yet finalised. Always "" for batch engines. */
  interimTranscript: string;

  /** Mic is open and capturing. */
  isListening: boolean;
  /** Mic closed, engine is turning the captured audio into text (batch only). */
  isTranscribing: boolean;

  /**
   * Engine can run on this device at all — browser has the Web Speech API, or
   * the WASM runtime + model loaded successfully. False means show the caller a
   * "can't do speech here" state.
   */
  supported: boolean;
  /** Engine is still fetching its runtime / model; keep the mic disabled. */
  isLoading: boolean;
  /** Download progress while `isLoading`, or null when there's no signal. */
  progress: SttProgress | null;

  error: string | null;
}

export interface EngineHookArgs {
  /**
   * This engine is the one selected for the current language. When false the
   * hook must stay dormant — no mic, no download, no model in memory.
   */
  active: boolean;
  /** BCP-47 tag, e.g. "en-US" / "hi-IN". Meaning depends on the engine. */
  speechLang: string;
  /** Tutor language name ("English" / "Hindi") — the backend keys models by it. */
  language: string;
}
