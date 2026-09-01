import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../../services/api";
import type { EngineHookArgs, TutorStt } from "./types";

// Offline STT for the Indian languages: the backend's /api/stt route runs
// sherpa-onnx + AI4Bharat's IndicConformer (one multilingual model). The
// browser records a short clip and POSTs it on mic release.
const STT_URL = `${API_BASE_URL}/api/stt`;

const TARGET_RATE = 16000;

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

/**
 * Offline STT for the Indian languages via the backend `/api/stt` route
 * (IndicConformer). Batch: audio is captured while the mic is open and the
 * whole clip is sent for decoding on `stopListening`, so `isTranscribing` is
 * true for ~1 s and there are no live partials.
 */
export function useIndicSpeechToText({ active }: EngineHookArgs): TutorStt {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [transcript, setTranscript] = useState("");

  const chunksRef = useRef<Float32Array[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const nodeRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  // When an Indian language is selected, ping the backend — it lazily loads the
  // model and tells us when it's ready (or that it isn't installed).
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    setReady(false);
    setError(null);

    (async () => {
      try {
        const res = await fetch(STT_URL, { method: "GET" });
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
  }, [active]);

  const teardownMic = useCallback(() => {
    nodeRef.current?.disconnect();
    sourceRef.current?.disconnect();
    nodeRef.current = null;
    sourceRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void audioCtxRef.current?.close();
    audioCtxRef.current = null;
  }, []);

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
      node.onaudioprocess = (ev) => {
        const input = ev.inputBuffer.getChannelData(0);
        chunksRef.current.push(downsample(new Float32Array(input), inRate));
      };

      source.connect(node);
      node.connect(ctx.destination); // ScriptProcessor needs a sink to tick
      setIsListening(true);
    } catch (err) {
      teardownMic();
      setError(err instanceof Error ? err.message : "Couldn't access the microphone.");
    }
  }, [ready, isListening, teardownMic]);

  const stopListening = useCallback(async () => {
    if (!isListening) return;
    teardownMic();
    setIsListening(false);

    const parts = chunksRef.current;
    chunksRef.current = [];
    const total = parts.reduce((n, p) => n + p.length, 0);
    if (total === 0) return;

    const samples = new Float32Array(total);
    let offset = 0;
    for (const p of parts) {
      samples.set(p, offset);
      offset += p.length;
    }

    setIsTranscribing(true);
    try {
      const res = await fetch(STT_URL, {
        method: "POST",
        headers: { "Content-Type": "audio/wav" },
        body: encodeWav(samples),
      });
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        setError(`Transcription failed (${res.status}). ${body}`);
        return;
      }
      const data = (await res.json()) as { text?: string };
      const text = (data.text || "").trim();
      if (text) setTranscript((prev) => (prev ? `${prev} ${text}` : text));
    } catch {
      setError("Can't reach the tutor backend for speech recognition.");
    } finally {
      setIsTranscribing(false);
    }
  }, [isListening, teardownMic]);

  const resetTranscript = useCallback(() => {
    setTranscript("");
  }, []);

  useEffect(() => {
    if (!active && isListening) void stopListening();
  }, [active, isListening, stopListening]);

  return {
    startListening: () => void startListening(),
    stopListening: () => void stopListening(),
    resetTranscript,
    transcript,
    interimTranscript: "",
    isListening,
    isTranscribing,
    supported: !error,
    isLoading: active && !ready && !error,
    progress: null,
    error,
  };
}
