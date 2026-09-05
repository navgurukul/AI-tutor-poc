import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../../services/api";

const TTS_URL = `${API_BASE_URL}/api/tts`;

export interface BackendTts {
  /** Queue a sentence. Sentences are spoken in the order they arrive. */
  speak: (text: string) => void;
  /** Drop everything queued and stop the audio that's playing. */
  stop: () => void;
  isReady: boolean;
  isPlaying: boolean;
  error: string | null;
}

/**
 * Text-to-speech through the backend's /api/tts (sherpa-onnx running a Piper
 * voice per language). The browser only plays the WAV it gets back — no model
 * download, no WASM, nothing cached client-side.
 *
 * The tutor streams its answer sentence by sentence, so `speak` is called many
 * times per turn. Two queues keep that orderly: sentences are synthesized one
 * request at a time (parallel requests would just contend for the same backend
 * CPU), and finished clips play back-to-back. `stop` bumps a sequence number
 * that both loops check, so an in-flight request can't resurrect audio after a
 * barge-in.
 */
export function useBackendTts(language: string): BackendTts {
  const [isReady, setIsReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const synthesisQueueRef = useRef<string[]>([]);
  const audioQueueRef = useRef<Blob[]>([]);
  const playingRef = useRef(false);
  const synthesizingRef = useRef(false);
  // Every <audio> the playback loop has created and not yet finished. stop()
  // pauses all of them — covers the microtask gap where one element ended and
  // the next hasn't been assigned yet.
  const liveAudioRef = useRef<Set<HTMLAudioElement>>(new Set());
  // Resolver for the promise the playback loop is awaiting, so stop() can
  // unwedge it (pausing an <audio> fires no event).
  const pendingResolveRef = useRef<(() => void) | null>(null);
  // Serialises requests: only one synthesis is ever in flight.
  const synthChainRef = useRef<Promise<unknown>>(Promise.resolve());
  // Bumped by stop(). Loops capture it before an await and bail if it changed.
  const cancelSeqRef = useRef(0);

  // Ask whether this language's voice is installed. Also triggers the backend's
  // lazy model load, so the first real sentence doesn't pay for it.
  useEffect(() => {
    let active = true;
    setIsReady(false);
    setError(null);

    (async () => {
      try {
        const response = await fetch(
          `${TTS_URL}?language=${encodeURIComponent(language)}`,
        );
        if (!active) return;
        if (!response.ok) {
          setError(`Voice check failed (${response.status}).`);
          return;
        }
        const data = await response.json();
        if (!active) return;
        if (data.ready) {
          setIsReady(true);
        } else {
          setError(
            `No offline ${language} voice on the backend. Run scripts/setup.ps1.`,
          );
        }
      } catch {
        if (active) setError("Can't reach the tutor backend for speech.");
      }
    })();

    return () => {
      active = false;
    };
  }, [language]);

  const requestWav = useCallback(
    async (text: string): Promise<Blob> => {
      const response = await fetch(
        `${TTS_URL}?language=${encodeURIComponent(language)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        },
      );
      if (!response.ok) {
        const detail = await response.text().catch(() => "");
        throw new Error(`TTS failed (${response.status}). ${detail}`);
      }
      return response.blob();
    },
    [language],
  );

  const synthesize = useCallback(
    (text: string): Promise<Blob> => {
      const run = synthChainRef.current.then(() => requestWav(text));
      synthChainRef.current = run.catch(() => undefined);
      return run;
    },
    [requestWav],
  );

  const playQueue = useCallback(async () => {
    if (playingRef.current) return;
    playingRef.current = true;
    const seq = cancelSeqRef.current;
    setIsPlaying(true);
    try {
      while (audioQueueRef.current.length > 0) {
        if (seq !== cancelSeqRef.current) break;
        const blob = audioQueueRef.current.shift();
        if (!blob) break;
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        liveAudioRef.current.add(audio);
        await new Promise<void>((resolve) => {
          pendingResolveRef.current = resolve;
          const done = () => {
            audio.onended = null;
            audio.onerror = null;
            liveAudioRef.current.delete(audio);
            if (pendingResolveRef.current === resolve) pendingResolveRef.current = null;
            URL.revokeObjectURL(url);
            resolve();
          };
          audio.onended = done;
          audio.onerror = done;
          if (seq !== cancelSeqRef.current) {
            done();
            return;
          }
          audio.play().catch(done);
        });
      }
    } finally {
      if (seq === cancelSeqRef.current) {
        playingRef.current = false;
        setIsPlaying(false);
      }
    }
  }, []);

  const processSynthesisQueue = useCallback(async () => {
    if (synthesizingRef.current) return;
    synthesizingRef.current = true;
    const seq = cancelSeqRef.current;
    try {
      while (synthesisQueueRef.current.length > 0) {
        if (seq !== cancelSeqRef.current) break;
        const text = synthesisQueueRef.current.shift();
        if (!text) continue;
        try {
          const blob = await synthesize(text);
          if (seq !== cancelSeqRef.current) break;
          audioQueueRef.current.push(blob);
          if (!playingRef.current) void playQueue();
        } catch (err) {
          console.error("TTS synthesis error:", err);
          setError(err instanceof Error ? err.message : "Speech failed.");
        }
      }
    } finally {
      if (seq === cancelSeqRef.current) synthesizingRef.current = false;
    }
  }, [synthesize, playQueue]);

  const speak = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      synthesisQueueRef.current.push(trimmed);
      void processSynthesisQueue();
    },
    [processSynthesisQueue],
  );

  const stop = useCallback(() => {
    cancelSeqRef.current += 1;
    synthesisQueueRef.current = [];
    audioQueueRef.current = [];
    playingRef.current = false;
    synthesizingRef.current = false;
    pendingResolveRef.current?.();
    pendingResolveRef.current = null;
    for (const a of liveAudioRef.current) {
      a.onended = null;
      a.onerror = null;
      a.pause();
      a.src = "";
    }
    liveAudioRef.current.clear();
    setIsPlaying(false);
  }, []);

  // A language switch mid-answer must not leave the previous voice talking.
  useEffect(() => stop, [language, stop]);

  return { speak, stop, isReady, isPlaying, error };
}
