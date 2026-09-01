import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../../services/api";

const TTS_URL = `${API_BASE_URL}/api/tts`;

export interface BackendTtsApi {
  /** Queue a sentence. Sentences play back-to-back in call order. */
  speak: (text: string) => void;
  /** Stop the current sentence and drop everything queued. */
  cancel: () => void;
  /** Resume the AudioContext from a user gesture (the mic tap). */
  primeAudio: () => void;
  isSupported: boolean;
  isReady: boolean;
  isSpeaking: boolean;
  voiceMissing: boolean;
  /** The backend voice model is still loading (first request only). */
  voiceLoading: boolean;
  voiceDownloadProgress: { loaded: number; total: number } | null;
}

/**
 * Text-to-speech via the backend `/api/tts` route (sherpa-onnx + a Piper VITS
 * voice). Each sentence is POSTed as it comes off the LLM stream; the WAV comes
 * back and is played in call order, gaplessly, so the answer is spoken
 * sentence-by-sentence while the rest is still being written.
 */
export function useBackendTts(active: boolean): BackendTtsApi {
  const isSupported =
    typeof AudioContext !== "undefined" ||
    typeof (globalThis as { webkitAudioContext?: unknown }).webkitAudioContext !== "undefined";

  const [failed, setFailed] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceLoading, setVoiceLoading] = useState(false);

  const ctxRef = useRef<AudioContext | null>(null);
  const seqRef = useRef(0);
  const minValidSeqRef = useRef(1); // bumped on cancel; drop anything older
  const queueRef = useRef<number[]>([]); // seqs waiting to play, in order
  const arrivedRef = useRef<Map<number, AudioBuffer>>(new Map());
  const playingRef = useRef(false);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);

  const ensureCtx = useCallback((): AudioContext => {
    if (!ctxRef.current) {
      const AC: typeof AudioContext =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      ctxRef.current = new AC();
    }
    if (ctxRef.current.state === "suspended") void ctxRef.current.resume();
    return ctxRef.current;
  }, []);

  const primeAudio = useCallback(() => {
    try {
      ensureCtx();
    } catch {
      /* no AudioContext on this device */
    }
  }, [ensureCtx]);

  const pump = useCallback(() => {
    if (playingRef.current) return;
    const next = queueRef.current[0];
    if (next === undefined) return;
    const buf = arrivedRef.current.get(next);
    if (!buf) return; // not synthesised yet

    queueRef.current.shift();
    arrivedRef.current.delete(next);
    playingRef.current = true;
    setIsSpeaking(true);

    const ctx = ensureCtx();
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.onended = () => {
      playingRef.current = false;
      sourceRef.current = null;
      if (queueRef.current.length === 0 && arrivedRef.current.size === 0) setIsSpeaking(false);
      pump();
    };
    sourceRef.current = src;
    src.start();
  }, [ensureCtx]);

  // Ping the backend when this engine goes active so the voice model warms.
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    setFailed(false);
    setVoiceLoading(true);
    (async () => {
      try {
        const res = await fetch(TTS_URL, { method: "GET" });
        if (cancelled) return;
        const data = (await res.json().catch(() => ({}))) as { ready?: boolean };
        if (!res.ok || !data.ready) setFailed(true);
      } catch {
        if (!cancelled) setFailed(true);
      } finally {
        if (!cancelled) setVoiceLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [active]);

  useEffect(() => {
    return () => {
      try {
        sourceRef.current?.stop();
      } catch {
        /* already stopped */
      }
      void ctxRef.current?.close();
      ctxRef.current = null;
    };
  }, []);

  const cancel = useCallback(() => {
    minValidSeqRef.current = seqRef.current + 1;
    queueRef.current = [];
    arrivedRef.current.clear();
    try {
      sourceRef.current?.stop();
    } catch {
      /* already stopped */
    }
    sourceRef.current = null;
    playingRef.current = false;
    setIsSpeaking(false);
  }, []);

  const speak = useCallback(
    (text: string) => {
      const phrase = text.trim();
      if (!phrase || failed) return;
      const seq = ++seqRef.current;
      queueRef.current.push(seq);

      (async () => {
        try {
          const res = await fetch(TTS_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: phrase }),
          });
          if (!res.ok) throw new Error(`tts ${res.status}`);
          if (seq < minValidSeqRef.current) return; // cancelled while in flight
          const bytes = await res.arrayBuffer();
          const buf = await ensureCtx().decodeAudioData(bytes);
          if (seq < minValidSeqRef.current) return;
          arrivedRef.current.set(seq, buf);
          pump();
        } catch (err) {
          console.warn("[tts] synth failed:", err);
          queueRef.current = queueRef.current.filter((s) => s !== seq);
          pump();
        }
      })();
    },
    [failed, ensureCtx, pump],
  );

  return {
    speak,
    cancel,
    primeAudio,
    isSupported: isSupported && !failed,
    isReady: true,
    isSpeaking,
    voiceMissing: failed,
    voiceLoading,
    voiceDownloadProgress: null,
  };
}
