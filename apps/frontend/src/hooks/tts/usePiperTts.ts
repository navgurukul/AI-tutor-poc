import { useCallback, useEffect, useRef, useState } from "react";
import { getCachedOrFetch } from "./voiceCache";

/**
 * Piper WASM text-to-speech, vendored from react-sts-hooks `usePiper`.
 *
 * Why a local copy instead of the library hook: `usePiper`'s `resetTTS` only
 * empties the pending queues — it has no handle on the `Audio` element already
 * playing, and its synthesis `while`-loop keeps pushing the sentence it was
 * mid-`await` on. So "Stop audio" / "Voice off" didn't actually stop the voice.
 * This version keeps the exact same worker protocol and asset layout
 * (`/piper-wasm/…`, the react-sts-setup files) but adds a real `stop()`:
 *   - bumps a cancel token the synth + playback loops check after every await
 *     (and in their `finally`, before touching shared state),
 *   - pauses and detaches *every* live `Audio` element and resolves the playback
 *     loop's pending wait so it unwinds cleanly,
 *   - clears both queues.
 *
 * Streaming is unchanged from upstream: `speak(sentence)` is fire-and-forget —
 * it appends to `synthesisQueueRef` and returns. Sentences are synthesized
 * serially (one `generate` in flight at a time) and their audio played
 * back-to-back, so the first sentence is speaking while the LLM is still
 * writing the rest.
 */
export interface PiperTtsConfig {
  /** URL to the `.onnx` voice model (served from public/models/). */
  voiceModelUrl: string;
  /** URL to the matching `.json` voice config. */
  voiceConfigUrl: string;
  /**
   * A realistic sentence synthesized once at load, behind `isLoading`, so the
   * first *real* answer doesn't pay onnxruntime-web's cold first-inference cost
   * (WASM JIT + arena allocation) — that was seconds of the first-audio delay.
   */
  warmupText?: string;
  /** Where the Piper WASM worker + phonemizer assets live. Default `/piper-wasm`. */
  assetsBaseUrl?: string;
}

export interface PiperTtsApi {
  /** Queue a sentence. Fire-and-forget; queued sentences play in order, gaplessly. */
  speak: (text: string) => void;
  /** Stop now: silence the current sentence and drop everything queued. */
  stop: () => void;
  isReady: boolean;
  isLoading: boolean;
  isPlaying: boolean;
  error: string | null;
  downloadProgress: { loaded: number; total: number } | null;
}

interface WorkerMessage {
  kind: "output" | "stderr";
  file?: Blob;
  message?: string;
}

export function usePiperTts(config: PiperTtsConfig | null): PiperTtsApi {
  const [isReady, setIsReady] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState<
    { loaded: number; total: number } | null
  >(null);

  const workerRef = useRef<Worker | null>(null);
  const audioQueueRef = useRef<Blob[]>([]);
  const synthesisQueueRef = useRef<string[]>([]);
  const playingRef = useRef(false);
  const synthesizingRef = useRef(false);
  // Every <audio> the playback loop has created and not yet finished. stop()
  // pauses all of them — covers the microtask gap where one element ended and
  // the next hasn't been assigned to a "current" ref yet.
  const liveAudioRef = useRef<Set<HTMLAudioElement>>(new Set());
  // Resolver for the promise the playback loop is currently awaiting, so stop()
  // can unwedge it (pausing an <audio> fires no event).
  const pendingResolveRef = useRef<(() => void) | null>(null);
  // Serialises `generate` calls: only one is ever in flight, so stop() + a new
  // speak() during synthesis can't leave two listeners racing for one message.
  const synthChainRef = useRef<Promise<unknown>>(Promise.resolve());
  // Bumped by stop(). Loops capture it before an await and bail — in the body
  // and in `finally` — if it changed since.
  const cancelSeqRef = useRef(0);

  const modelUrl = config?.voiceModelUrl;
  const configUrl = config?.voiceConfigUrl;
  const warmupText = config?.warmupText;
  const base = config?.assetsBaseUrl ?? "/piper-wasm";

  useEffect(() => {
    if (!modelUrl || !configUrl) return;
    let active = true;
    const blobUrls: string[] = [];

    setIsReady(false);
    setIsLoading(true);
    setError(null);
    setDownloadProgress({ loaded: 0, total: 100 });

    (async () => {
      try {
        const modelBlob = await getCachedOrFetch(modelUrl, (loaded, total) => {
          if (active) setDownloadProgress({ loaded, total });
        });
        const configBlob = await getCachedOrFetch(configUrl);
        if (!active) return;

        const mUrl = URL.createObjectURL(modelBlob);
        const cUrl = URL.createObjectURL(configBlob);
        blobUrls.push(mUrl, cUrl);

        const worker = new Worker(`${base}/piper_worker.js`);
        workerRef.current = worker;

        // The worker only ever reports a failed init as a stderr line, so
        // without this the hook would wait for an "output" that never comes and
        // the UI would sit on the download bar forever.
        const failInit = (message: string) => {
          worker.removeEventListener("message", onInit);
          console.error("[Piper]", message);
          if (active) {
            setIsReady(false);
            setIsLoading(false);
            setDownloadProgress(null);
            setError(message);
          }
        };

        const onInit = (event: MessageEvent<WorkerMessage>) => {
          const data = event.data;
          if (data.kind === "output") {
            worker.removeEventListener("message", onInit);
            if (active) {
              setIsReady(true);
              setIsLoading(false);
              setDownloadProgress(null);
            }
          } else if (data.kind === "stderr") {
            const message = data.message ?? "";
            if (message.startsWith("Init failed:")) {
              failInit(message);
            } else {
              console.log("[Piper]", message);
            }
          }
        };
        worker.addEventListener("message", onInit);
        // Catches the worker script itself failing to load/parse, which never
        // reaches the message handler above.
        worker.addEventListener("error", (event) => {
          failInit(`Piper worker error: ${event.message || "failed to load"}`);
        });
        worker.postMessage({
          kind: "init",
          input: warmupText || "Warmup",
          modelUrl: mUrl,
          modelConfigUrl: cUrl,
          piperPhonemizeJsUrl: `${base}/piper_phonemize.js`,
          piperPhonemizeWasmUrl: `${base}/piper_phonemize.wasm`,
          piperPhonemizeDataUrl: `${base}/piper_phonemize.data`,
          onnxruntimeUrl: `${window.location.origin}/`,
          blobs: {},
        });
      } catch (err) {
        if (active) {
          setIsReady(false);
          setIsLoading(false);
          setError(err instanceof Error ? err.message : "Failed to initialize Piper");
        }
      }
    })();

    return () => {
      active = false;
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
      workerRef.current?.terminate();
      workerRef.current = null;
      blobUrls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [modelUrl, configUrl, warmupText, base]);

  // One raw `generate` round-trip to the worker.
  const generate = useCallback(
    (text: string): Promise<Blob> => {
      const worker = workerRef.current;
      if (!worker) return Promise.reject(new Error("Piper worker not initialized"));
      return new Promise<Blob>((resolve, reject) => {
        const onMessage = (event: MessageEvent<WorkerMessage>) => {
          const data = event.data;
          if (data.kind === "output") {
            worker.removeEventListener("message", onMessage);
            if (data.file) resolve(data.file);
            else reject(new Error("Piper returned no audio"));
          } else if (data.kind === "stderr") {
            console.log("[Piper]", data.message);
          }
        };
        worker.addEventListener("message", onMessage);
        worker.postMessage({
          kind: "generate",
          input: text,
          modelUrl,
          modelConfigUrl: configUrl,
          piperPhonemizeJsUrl: `${base}/piper_phonemize.js`,
          piperPhonemizeWasmUrl: `${base}/piper_phonemize.wasm`,
          piperPhonemizeDataUrl: `${base}/piper_phonemize.data`,
          onnxruntimeUrl: `${window.location.origin}/`,
          blobs: {},
        });
      });
    },
    [modelUrl, configUrl, base],
  );

  // Chain `generate` calls so only one is in flight at a time.
  const synthesize = useCallback(
    (text: string): Promise<Blob> => {
      const run = synthChainRef.current.then(() => generate(text));
      synthChainRef.current = run.catch(() => undefined);
      return run;
    },
    [generate],
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
          console.error("Piper synthesis error:", err);
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

  return { speak, stop, isReady, isLoading, isPlaying, error, downloadProgress };
}
