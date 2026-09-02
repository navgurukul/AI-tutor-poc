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

/** Average-resample a mono Float32 buffer to 16 kHz. */
function downsample(buffer: Float32Array, inRate: number): Float32Array {
  if (inRate === TARGET_RATE) return buffer;
  const ratio = inRate / TARGET_RATE;
  const outLen = Math.round(buffer.length / ratio);
  const out = new Float32Array(outLen);
  let iOut = 0;
  let iIn = 0;
  while (iOut < outLen) {
    const nextIn = Math.round((iOut + 1) * ratio);
    let acc = 0;
    let count = 0;
    for (let i = iIn; i < nextIn && i < buffer.length; i++) {
      acc += buffer[i];
      count++;
    }
    out[iOut++] = count ? acc / count : 0;
    iIn = nextIn;
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

async function postWav(samples: Float32Array, language: string): Promise<string> {
  const res = await fetch(`${STT_URL}?language=${encodeURIComponent(language)}`, {
    method: "POST",
    headers: { "Content-Type": "audio/wav" },
    body: encodeWav(samples),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Transcription failed (${res.status}). ${body}`);
  }
  const data = (await res.json()) as { text?: string };
  return (data.text || "").trim();
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
  const partialInFlightRef = useRef(false);
  const lastPartialSamplesRef = useRef(0);
  const speechHeardRef = useRef(false);
  const lastVoiceAtRef = useRef(0);

  // When this engine's language is selected, ping the backend — it lazily loads
  // that language's model and tells us when it's ready (or that it isn't installed).
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    setReady(false);
    setError(null);

    (async () => {
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
        if (data.ready) setReady(true);
        else
          setError(
            "Offline speech model isn't installed on the backend. Re-run scripts/setup.ps1.",
          );
      } catch {
        if (!cancelled) setError("Can't reach the tutor backend for speech recognition.");
      }
    })();

    return () => {
      cancelled = true;
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
      teardownMic();
      setIsListening(false);

      const samples = transcribe ? collect(FINAL_MAX_SEC) : new Float32Array(0);
      chunksRef.current = [];
      setInterimTranscript("");
      if (!transcribe || samples.length === 0) return;

      setIsTranscribing(true);
      const clipSeconds = samples.length / TARGET_RATE;
      const startedAt = performance.now();
      void postWav(samples, languageRef.current)
        .then((text) => {
          console.log(
            `[timing] STT round-trip: ${(performance.now() - startedAt).toFixed(0)}ms ` +
              `(${clipSeconds.toFixed(1)}s clip -> ${text.length} chars)`,
          );
          if (text) setTranscript((prev) => (prev ? `${prev} ${text}` : text));
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
    if (!ready || isListening) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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

      const inRate = ctx.sampleRate;
      chunksRef.current = [];
      finishedRef.current = false;
      partialInFlightRef.current = false;
      lastPartialSamplesRef.current = 0;
      speechHeardRef.current = false;
      lastVoiceAtRef.current = performance.now();
      setInterimTranscript("");

      node.onaudioprocess = (ev) => {
        const input = ev.inputBuffer.getChannelData(0);
        chunksRef.current.push(downsample(new Float32Array(input), inRate));
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
        const total = chunksRef.current.reduce((n, p) => n + p.length, 0);
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
      teardownMic();
      setError(err instanceof Error ? err.message : "Couldn't access the microphone.");
    }
  }, [ready, isListening, teardownMic, finish, collect]);

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
