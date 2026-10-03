import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../../services/api";
import type { EngineHookArgs, TutorStt } from "./types";

// Offline STT for the Indian languages: the backend's /api/stt route runs
// sherpa-onnx + AI4Bharat's IndicConformer (one multilingual model).
//
// IndicConformer is a *batch* model — it can't stream token-by-token like the
// Web Speech API. To still feel live we (a) re-decode the growing clip every
// ~1.1 s while the mic is open and show it as interim text, and (b) run a small
// energy VAD so the turn auto-submits after a pause, no "Send" tap needed.
const STT_URL = `${API_BASE_URL}/api/stt`;

const TARGET_RATE = 16000;
// Re-decode the clip-so-far this often for the live interim transcript.
const PARTIAL_INTERVAL_MS = 1100;
// Don't fire a partial unless this much *new* audio has arrived since the last.
const PARTIAL_MIN_NEW_SEC = 0.4;
// Cap what a partial re-decodes (decode time grows with length); the final
// decode still gets the whole clip (up to FINAL_MAX_SEC).
const PARTIAL_MAX_SEC = 15;
const FINAL_MAX_SEC = 30;
// Energy VAD: a frame louder than this counts as speech; once speech has been
// heard, this much trailing quiet ends the utterance.
const SPEECH_RMS = 0.012;
const SILENCE_HANGOVER_MS = 1100;
// Spacing for the readiness check's retries on a network failure -- see its
// own comment below for why it retries at all.
const READINESS_RETRY_DELAYS_MS = [500, 1500, 3000];

// IndicConformer's vocabulary has no punctuation tokens at all -- checked
// directly against models/indicconformer/tokens.txt, which holds subword
// pieces across several scripts and not one Devanagari danda (।) or ASCII
// stop among them. The model was simply never trained to emit one, so a long
// dictation comes back as one unbroken run of words no matter what settings
// are used. A pause is the only signal left to guess where a sentence ends:
// the final clip is split at internal pauses (see splitOnPauses) and each
// piece decoded separately, then rejoined with a danda in between.
const DANDA = "।";
// An internal pause at least this long is treated as a likely sentence break.
// MEASURED WRONG at 500ms 2026-09-29: someone dictating a passage carefully
// -- reading it aloud rather than talking naturally -- pauses 500ms+ between
// ordinary WORDS and phrases too, not just between sentences, so that value
// caught nearly every word gap and produced a danda after almost every few
// words. Raised close to the SILENCE_HANGOVER_MS ceiling (1100ms, which ends
// the WHOLE recording) to leave only a narrow band of "long enough to be a
// sentence break, not long enough to end the utterance" -- there may be no
// threshold that cleanly separates the two for every speaker; a pause-timing
// heuristic has a real ceiling here, not just a tuning problem.
const SENTENCE_PAUSE_MS = 900;
// RMS scan window used to find those pauses. Coarse on purpose: this only
// has to find silence, not do speech recognition.
const PAUSE_SCAN_FRAME_MS = 30;
const PAUSE_SCAN_FRAME_SAMPLES = Math.round((PAUSE_SCAN_FRAME_MS / 1000) * TARGET_RATE);
// Never split into a sliver shorter than this -- each segment is its own HTTP
// + decode call, which has fixed overhead not worth paying for half a word.
// Raised alongside SENTENCE_PAUSE_MS: a "sentence" should be more than a
// couple of words, so a segment barely over a second is more likely a
// spurious split than a real one.
const MIN_SEGMENT_S = 1.2;
const MIN_SEGMENT_SAMPLES = Math.round(MIN_SEGMENT_S * TARGET_RATE);

/** Resample a mono Float32 buffer to 16 kHz, the rate IndicConformer expects.
 *
 * Two directions, because the capture rate is the device's, not ours. Asking
 * for a 16 kHz AudioContext is a request, not a guarantee: a laptop mic
 * usually gives 44.1/48 kHz, and a Bluetooth headset in call mode gives 8 kHz.
 *
 * Downwards, each output sample is the average of the input window it covers,
 * which low-passes as it decimates. Upwards, neighbours are interpolated. The
 * upward case used to fall into the averaging branch with an EMPTY window and
 * write a zero between every real sample -- a buzzing, aliased copy of the
 * speech, which is what makes a recogniser repeat words and stretch vowels.
 */
function resampleTo16k(buffer: Float32Array, inRate: number): Float32Array {
  if (inRate === TARGET_RATE || buffer.length === 0) return buffer;
  const ratio = inRate / TARGET_RATE;
  const outLen = Math.max(1, Math.round(buffer.length / ratio));
  const out = new Float32Array(outLen);

  if (ratio >= 1) {
    let iIn = 0;
    for (let iOut = 0; iOut < outLen; iOut++) {
      const nextIn = Math.min(buffer.length, Math.round((iOut + 1) * ratio));
      let acc = 0;
      let count = 0;
      for (let i = iIn; i < nextIn; i++) {
        acc += buffer[i];
        count++;
      }
      out[iOut] = count ? acc / count : buffer[Math.min(iIn, buffer.length - 1)];
      iIn = nextIn;
    }
    return out;
  }

  for (let iOut = 0; iOut < outLen; iOut++) {
    const pos = iOut * ratio;
    const i0 = Math.floor(pos);
    const i1 = Math.min(buffer.length - 1, i0 + 1);
    const frac = pos - i0;
    out[iOut] = buffer[i0] * (1 - frac) + buffer[i1] * frac;
  }
  return out;
}


/** Float32 [-1,1] mono @ 16 kHz -> a 16-bit PCM WAV blob. */
function encodeWav(samples: Float32Array): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  const dataLen = samples.length * 2;
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataLen, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, TARGET_RATE, true);
  view.setUint32(28, TARGET_RATE * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeStr(36, "data");
  view.setUint32(40, dataLen, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

async function postWav(
  samples: Float32Array,
  language: string,
  requestId?: string,
): Promise<string> {
  const res = await fetch(`${STT_URL}?language=${encodeURIComponent(language)}`, {
    method: "POST",
    // Only the final (non-partial) call passes a requestId -- it's what lets
    // the backend's /client-timing call below be joined, in stt.jsonl, with
    // the server-side line for this same clip. Partial/interim re-decodes
    // don't bother: nothing calls client-timing for them.
    headers: requestId
      ? { "Content-Type": "audio/wav", "X-Request-Id": requestId }
      : { "Content-Type": "audio/wav" },
    body: encodeWav(samples),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Transcription failed (${res.status}). ${body}`);
  }
  const data = (await res.json()) as { text?: string };
  return (data.text || "").trim();
}

/** Best-effort: tells the backend how long the student actually waited (mic
 * stop -> text on screen), including upload/download and the React update --
 * everything the server's own log can't see. Never awaited by the caller and
 * never surfaced as an error; a lost timing ping must not affect the UI. */
function reportClientTiming(payload: {
  request_id: string;
  client_total_ms: number;
  clip_seconds: number;
  chars: number;
  truncated: boolean;
  dropped_seconds?: number;
}): void {
  fetch(`${STT_URL}/client-timing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).catch(() => undefined);
}

/**
 * Split a mono 16 kHz clip into [start, end) sample ranges at internal
 * pauses, so each range can be decoded separately and rejoined with a danda
 * (see the DANDA/SENTENCE_PAUSE_MS comment above for why this exists at all).
 *
 * Covers the WHOLE clip -- every sample belongs to exactly one segment,
 * including the pause audio itself (harmless: the model decodes silence as
 * nothing). The common case, a short question with no mid-utterance pause,
 * returns a single segment covering the entire clip -- same one decode call
 * as before this existed.
 */
function splitOnPauses(samples: Float32Array): Array<[number, number]> {
  const boundaries: number[] = [];
  let speechSeen = false;
  let silenceStart = -1; // sample index the current silence run began at, or -1
  let segmentStart = 0;

  for (let i = 0; i < samples.length; i += PAUSE_SCAN_FRAME_SAMPLES) {
    const end = Math.min(samples.length, i + PAUSE_SCAN_FRAME_SAMPLES);
    let sum = 0;
    for (let j = i; j < end; j++) sum += samples[j] * samples[j];
    const isSpeech = Math.sqrt(sum / (end - i)) > SPEECH_RMS;

    if (isSpeech) {
      speechSeen = true;
      silenceStart = -1;
      continue;
    }
    if (!speechSeen) continue; // leading silence before any speech -- not a break
    if (silenceStart === -1) silenceStart = i;
    const silenceMs = ((end - silenceStart) / TARGET_RATE) * 1000;
    if (
      silenceMs >= SENTENCE_PAUSE_MS &&
      silenceStart - segmentStart >= MIN_SEGMENT_SAMPLES
    ) {
      boundaries.push(silenceStart);
      segmentStart = silenceStart;
      silenceStart = -1; // one boundary per pause, not one per frame of it
    }
  }

  const segments: Array<[number, number]> = [];
  let start = 0;
  for (const b of boundaries) {
    segments.push([start, b]);
    start = b;
  }
  segments.push([start, samples.length]);

  // Drop segments that are pure silence before anything is sent for decoding
  // -- most importantly the trailing one. `finish()` only runs once
  // SILENCE_HANGOVER_MS (1.1s) of quiet has already been heard, so that
  // trailing pause is baked into every single recording, not just a long
  // dictation. Without this filter, a plain one-sentence question would
  // ALSO come back as two segments (the answer, then ~1.1s of silence) and
  // pay for a second, wasted decode call every time.
  const withSpeech = segments.filter(([s, e]) => {
    let sum = 0;
    for (let i = s; i < e; i++) sum += samples[i] * samples[i];
    return Math.sqrt(sum / (e - s)) > SPEECH_RMS;
  });
  // Still return something even if every window came back quiet -- a
  // low-volume recording should get one decode attempt, not zero.
  return withSpeech.length ? withSpeech : segments.filter(([s, e]) => e > s);
}

/**
 * Offline STT for the Indian languages via the backend `/api/stt` route.
 * Live-ish: interim text while you speak (re-decode of the growing clip), plus
 * an energy VAD that ends the utterance on a pause so it auto-submits.
 */
export function useIndicSpeechToText({ active, language }: EngineHookArgs): TutorStt {
  // Latest language name for the backend `?language=`, read from the mic/timer
  // callbacks without adding it to every useCallback dep list.
  const languageRef = useRef(language);
  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");

  const chunksRef = useRef<Float32Array[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const nodeRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const finishedRef = useRef(false);
  // True from the moment a recording is being opened until it is finished, so
  // a second tap cannot open a second microphone into the same buffer.
  const startingRef = useRef(false);
  const partialInFlightRef = useRef(false);
  const lastPartialSamplesRef = useRef(0);
  const speechHeardRef = useRef(false);
  const lastVoiceAtRef = useRef(0);

  // When this engine's language is selected, ping the backend — it lazily loads
  // that language's model and tells us when it's ready (or that it isn't installed).
  //
  // Retries a few times on a network failure before giving up: this fires the
  // moment the page loads, which can race the backend's own startup or a
  // restart from `start.ps1`. Unlike the TTS voice check, `ready` here
  // actually gates the mic (`startListening` no-ops while it's false), so a
  // single lost race used to leave the mic silently unresponsive for the rest
  // of the session even after the backend came up a moment later. Does NOT
  // retry a real "not ready" or a non-OK status -- those are the backend
  // correctly saying the model genuinely is not there.
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    setReady(false);
    setError(null);

    const check = async (attempt: number) => {
      try {
        const res = await fetch(`${STT_URL}?language=${encodeURIComponent(language)}`);
        if (cancelled) return;
        if (!res.ok) {
          const body = await res.text().catch(() => "");
          setError(
            `Offline speech model unavailable (${res.status}). ${body || "Re-run scripts/setup.ps1."}`,
          );
          return;
        }
        const data = (await res.json()) as { ready?: boolean };
        if (cancelled) return;
        if (data.ready) {
          setReady(true);
          setError(null);
        } else {
          setError(
            "Offline speech model isn't installed on the backend. Re-run scripts/setup.ps1.",
          );
        }
      } catch {
        if (cancelled) return;
        const delay = READINESS_RETRY_DELAYS_MS[attempt];
        if (delay !== undefined) {
          timer = setTimeout(() => void check(attempt + 1), delay);
          return; // not yet a failure -- still trying
        }
        setError("Can't reach the tutor backend for speech recognition.");
      }
    };
    void check(0);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [active, language]);

  const teardownMic = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    nodeRef.current?.disconnect();
    sourceRef.current?.disconnect();
    nodeRef.current = null;
    sourceRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void audioCtxRef.current?.close();
    audioCtxRef.current = null;
  }, []);

  const collect = useCallback((maxSeconds: number): Float32Array => {
    const parts = chunksRef.current;
    const total = parts.reduce((n, p) => n + p.length, 0);
    const all = new Float32Array(total);
    let offset = 0;
    for (const p of parts) {
      all.set(p, offset);
      offset += p.length;
    }
    const cap = Math.round(maxSeconds * TARGET_RATE);
    return all.length > cap ? all.slice(all.length - cap) : all;
  }, []);

  // End the utterance. `transcribe: false` just drops the mic (language switch).
  const finish = useCallback(
    (transcribe: boolean) => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      startingRef.current = false;
      teardownMic();
      setIsListening(false);

      // Measured BEFORE collect() applies its cap and BEFORE chunksRef is
      // cleared below -- collect() silently drops everything older than the
      // last FINAL_MAX_SEC seconds, so this is the only point that can still
      // see how much (if any) speech that cap is about to throw away.
      const rawTotal = transcribe
        ? chunksRef.current.reduce((n, p) => n + p.length, 0)
        : 0;
      const samples = transcribe ? collect(FINAL_MAX_SEC) : new Float32Array(0);
      chunksRef.current = [];
      setInterimTranscript("");
      if (!transcribe || samples.length === 0) return;

      const capSamples = Math.round(FINAL_MAX_SEC * TARGET_RATE);
      const truncated = rawTotal > capSamples;
      const droppedSeconds = truncated ? (rawTotal - capSamples) / TARGET_RATE : 0;
      if (truncated) {
        console.warn(
          `[stt] utterance ran past the ${FINAL_MAX_SEC}s cap -- dropped ~` +
            `${droppedSeconds.toFixed(1)}s of speech from the START of this turn ` +
            `before it was ever sent for transcription`,
        );
      }

      setIsTranscribing(true);
      const clipSeconds = samples.length / TARGET_RATE;
      // Loudness travels with the timing line: a clip that is nearly silent, or
      // one that clips at 1.0, explains a bad transcript on its own.
      let sumSq = 0;
      let peak = 0;
      for (let i = 0; i < samples.length; i++) {
        sumSq += samples[i] * samples[i];
        if (Math.abs(samples[i]) > peak) peak = Math.abs(samples[i]);
      }
      const rms = samples.length ? Math.sqrt(sumSq / samples.length) : 0;
      // Ties this turn's server-side stt.jsonl line(s) to the client-timing
      // line reported below, once the round trip is known. One segment (the
      // common case: a short question, no mid-utterance pause) sends this id
      // as-is; more than one suffixes each so every decode call still gets
      // its own line, joinable by the shared `turnId:` prefix.
      const turnId = crypto.randomUUID();
      const segments = splitOnPauses(samples);
      const startedAt = performance.now();

      const decodeTurn = async (): Promise<string> => {
        const parts: string[] = [];
        for (let i = 0; i < segments.length; i++) {
          const [s, e] = segments[i];
          const segmentId = segments.length > 1 ? `${turnId}:seg${i}` : turnId;
          const part = await postWav(samples.slice(s, e), languageRef.current, segmentId);
          if (part) parts.push(part);
        }
        // The model itself never emits punctuation (see DANDA above) -- each
        // detected pause stands in for a full stop, and the trailing one
        // marks the end of the whole dictation.
        return parts.length ? parts.join(`${DANDA} `) + DANDA : "";
      };

      void decodeTurn()
        .then((text) => {
          const clientTotalMs = performance.now() - startedAt;
          console.log(
            `[timing] STT round-trip: ${clientTotalMs.toFixed(0)}ms ` +
              `(${clipSeconds.toFixed(1)}s clip, ${segments.length} segment(s), ` +
              `rms ${rms.toFixed(3)}, peak ${peak.toFixed(2)} -> ${text.length} chars)`,
          );
          if (text) setTranscript((prev) => (prev ? `${prev} ${text}` : text));
          // Fire-and-forget: this is the one number neither side alone can
          // produce -- upload + decode + download + the setTranscript above,
          // as the student actually experienced it, summed across every
          // segment this turn was split into.
          reportClientTiming({
            request_id: turnId,
            client_total_ms: Math.round(clientTotalMs),
            clip_seconds: Math.round(clipSeconds * 10) / 10,
            chars: text.length,
            truncated,
            dropped_seconds: truncated ? Math.round(droppedSeconds * 10) / 10 : undefined,
          });
        })
        .catch((err) => {
          setError(
            err instanceof Error && err.message.startsWith("Transcription failed")
              ? err.message
              : "Can't reach the tutor backend for speech recognition.",
          );
        })
        .finally(() => setIsTranscribing(false));
    },
    [teardownMic, collect],
  );

  const startListening = useCallback(async () => {
    // Guarded on a ref, not on `isListening`: setState is asynchronous, so two
    // taps in the same tick both saw `false` and opened two microphones.
    if (!ready || startingRef.current) return;
    startingRef.current = true;
    // Anything still open from a previous utterance goes first. A surviving
    // ScriptProcessor keeps firing into chunksRef.current -- which by then is
    // the NEW recording's array -- so the recogniser received the speaker
    // twice, interleaved, and returned every word twice.
    teardownMic();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: TARGET_RATE,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const AC: typeof AudioContext =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AC({ sampleRate: TARGET_RATE });
      audioCtxRef.current = ctx;
      if (ctx.state === "suspended") await ctx.resume();

      const source = ctx.createMediaStreamSource(stream);
      const node = ctx.createScriptProcessor(4096, 1, 1);
      sourceRef.current = source;
      nodeRef.current = node;

      // Captured per recording, not read from the ref on every callback: this
      // is the other half of the guard above.
      const chunks: Float32Array[] = [];
      chunksRef.current = chunks;
      const inRate = ctx.sampleRate;
      // Names the device and the rate actually in use. Without it a bad
      // transcript is indistinguishable between "wrong mic", "wrong rate" and
      // "the model is bad at this speaker".
      const track = stream.getAudioTracks()[0];
      const trackRate = track?.getSettings?.().sampleRate;
      console.log(
        `[stt] mic "${track?.label || "unknown"}" | track ${trackRate ?? "?"} Hz | ` +
          `AudioContext ${inRate} Hz -> ${TARGET_RATE} Hz ` +
          `${
            inRate === TARGET_RATE
              ? "(no resampling)"
              : inRate > TARGET_RATE
                ? "(downsampling)"
                : "(UPSAMPLING - low-rate mic)"
          }`,
      );
      finishedRef.current = false;
      partialInFlightRef.current = false;
      lastPartialSamplesRef.current = 0;
      speechHeardRef.current = false;
      lastVoiceAtRef.current = performance.now();
      setInterimTranscript("");

      node.onaudioprocess = (ev) => {
        const input = ev.inputBuffer.getChannelData(0);
        chunks.push(resampleTo16k(new Float32Array(input), inRate));
        let sum = 0;
        for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
        const rms = Math.sqrt(sum / input.length);
        if (rms > SPEECH_RMS) {
          speechHeardRef.current = true;
          lastVoiceAtRef.current = performance.now();
        }
      };

      source.connect(node);
      node.connect(ctx.destination); // ScriptProcessor needs a sink to tick
      setIsListening(true);

      pollRef.current = setInterval(() => {
        const now = performance.now();
        // Endpoint: speech was heard, then a stretch of quiet -> auto-submit.
        if (
          speechHeardRef.current &&
          now - lastVoiceAtRef.current > SILENCE_HANGOVER_MS &&
          !finishedRef.current
        ) {
          finish(true);
          return;
        }
        // Live interim: re-decode the clip-so-far.
        if (partialInFlightRef.current || finishedRef.current) return;
        const total = chunks.reduce((n, p) => n + p.length, 0);
        if (total - lastPartialSamplesRef.current < PARTIAL_MIN_NEW_SEC * TARGET_RATE) return;
        lastPartialSamplesRef.current = total;
        partialInFlightRef.current = true;
        void postWav(collect(PARTIAL_MAX_SEC), languageRef.current)
          .then((text) => {
            if (!finishedRef.current) setInterimTranscript(text);
          })
          .catch(() => undefined)
          .finally(() => {
            partialInFlightRef.current = false;
          });
      }, PARTIAL_INTERVAL_MS);
    } catch (err) {
      startingRef.current = false;
      teardownMic();
      setError(err instanceof Error ? err.message : "Couldn't access the microphone.");
    }
  }, [ready, teardownMic, finish, collect]);

  const resetTranscript = useCallback(() => {
    setTranscript("");
    setInterimTranscript("");
  }, []);

  useEffect(() => {
    if (!active && isListening) finish(false);
  }, [active, isListening, finish]);

  return {
    startListening: () => void startListening(),
    stopListening: () => finish(true),
    resetTranscript,
    transcript,
    interimTranscript,
    isListening,
    isTranscribing,
    supported: !error,
    isLoading: active && !ready && !error,
    progress: null,
    error,
  };
}
