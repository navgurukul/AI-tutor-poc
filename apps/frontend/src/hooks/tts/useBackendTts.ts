import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../../services/api";

const TTS_URL = `${API_BASE_URL}/api/tts`;
// Spacing for the readiness check's retries on a network failure -- see its
// own comment below for why it retries at all.
const READINESS_RETRY_DELAYS_MS = [500, 1500, 3000];

/**
 * No prebuffer: every clip plays the instant synthesis returns it.
 *
 * A cushion (hold the first clip until N are ready) was tried for Devanagari to
 * smooth a mid-answer stutter, since the model decodes at about the rate the
 * voice reads. On this box it backfired — it delayed the first word by a whole
 * synthesis AND turned the space between sentence 1 and 2 into a multi-second
 * hole while the next clip was generated. That gap was worse than the
 * occasional catch-up pause the cushion prevented. Any remaining gap between
 * sentences is the model still writing the next one, which no buffering here
 * can fix. See git history for PREBUFFER_BY_SCRIPT if it needs to come back.
 */

export interface BackendTts {
  /** Queue a sentence. Sentences are spoken in the order they arrive. */
  speak: (text: string) => void;
  /**
   * No more sentences are coming this turn. Kicks playback in case a tail clip
   * finished synthesising after the queue had already drained.
   */
  endTurn: () => void;
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
  // Set once any clip has actually played this session. Distinguishes "the
  // voice never worked" (worth a banner) from "one sentence's synthesis had a
  // transient hiccup mid-conversation, with everything before and after it
  // fine" (not worth one) -- see processSynthesisQueue's catch block. Reset on
  // a language switch, same as the rest of this hook's state.
  const hasSpokenRef = useRef(false);

  // Ask whether this language's voice is installed. Also triggers the backend's
  // lazy model load, so the first real sentence doesn't pay for it.
  //
  // Retries a few times on a network failure before giving up: this check
  // fires the moment the page loads, which can race the backend's own
  // startup (the Hindi voice alone took ~11s to warm on 2026-09-14) or a
  // restart from `start.ps1`. A single miss used to set the "didn't load"
  // banner for the rest of the session even once the backend came up a
  // moment later — `speak()` itself doesn't check this flag (see
  // useTutorTts's `isReady: true`), so audio kept working underneath a
  // banner insisting it wouldn't. Does NOT retry a real "ready: false" (no
  // voice installed) or a non-OK HTTP status -- those are the backend
  // answering, correctly, that the voice genuinely is not there.
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    setIsReady(false);
    setError(null);
    hasSpokenRef.current = false;

    const check = async (attempt: number) => {
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
          setError(null);
        } else {
          setError(
            `No offline ${language} voice on the backend. Run scripts/setup.ps1.`,
          );
        }
      } catch {
        if (!active) return;
        const delay = READINESS_RETRY_DELAYS_MS[attempt];
        if (delay !== undefined) {
          timer = setTimeout(() => void check(attempt + 1), delay);
          return; // not yet a failure -- still trying
        }
        setError("Can't reach the tutor backend for speech.");
      }
    };
    void check(0);

    return () => {
      if (timer) clearTimeout(timer);
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
            audio.onplaying = null;
            liveAudioRef.current.delete(audio);
            if (pendingResolveRef.current === resolve) pendingResolveRef.current = null;
            URL.revokeObjectURL(url);
            resolve();
          };
          audio.onended = done;
          audio.onerror = done;
          // Proof that sound actually started, as opposed to a clip that was
          // created, dropped, and counted as "spoken". This -- not a
          // successful synthesis response -- is what "the voice has worked
          // this session" means: synthesis returning bytes proves the backend
          // is fine, but says nothing about whether the browser actually
          // played them (autoplay policy, no output device, ...).
          audio.onplaying = () => {
            hasSpokenRef.current = true;
            console.log("[tts] clip playing");
          };
          if (seq !== cancelSeqRef.current) {
            done();
            return;
          }
          // A rejected play() used to be swallowed by `.catch(done)`, which is
          // indistinguishable from a working voice with the volume down: the
          // backend logs 200 for every sentence and the room stays silent.
          // Name the reason instead -- the browser's autoplay policy and a
          // missing output device need completely different fixes.
          audio.play().catch((err: unknown) => {
            const name = err instanceof Error ? err.name : "Error";
            const detail = err instanceof Error ? err.message : String(err);
            console.error(`[tts] playback failed (${name}): ${detail}`);
            // Same reasoning as the synthesis queue's catch block: once
            // audio has actually played this session, a LATER single clip
            // failing to play (a transient autoplay hiccup on a clip that
            // isn't the direct result of a click, one bad blob, ...) is not
            // "the voice didn't load" -- the voice plainly did. Surfacing the
            // same alarming banner for that mid-conversation is what was
            // reported 2026-09-15: two full grounded turns had already
            // played, yet the banner insisted the voice never loaded.
            if (!hasSpokenRef.current) {
              setError(
                name === "NotAllowedError"
                  ? "The browser blocked the answer audio. Tap the mic once, then ask again."
                  : `Couldn't play the answer audio (${name}). Check the output device and volume.`,
              );
            }
            done();
          });
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
          // One retry. After the app has sat idle for a few minutes, the first
          // request can go out on a keep-alive connection the backend already
          // closed and fail at the network level without ever reaching it --
          // seen 2026-09-11: every /api/tts in the backend log was 200, yet the
          // page reported the voice as broken. Browsers do not retry a POST
          // themselves, so a single retry is what keeps the sentence.
          const blob = await synthesize(text).catch(async () => {
            await new Promise((resolve) => setTimeout(resolve, 300));
            return synthesize(text);
          });
          if (seq !== cancelSeqRef.current) break;
          // A clip came back, so the voice works: clear any earlier failure
          // rather than leaving a "voice didn't load" banner up for the rest of
          // the session while the answer is being spoken underneath it.
          //
          // NOT where hasSpokenRef is set -- a synthesis response proves the
          // backend is fine, not that the browser actually played it (see
          // playQueue's onplaying handler, which is the real proof and the
          // signal that gates whether a LATER failure here is worth a banner).
          setError(null);
          audioQueueRef.current.push(blob);
          // Play whatever is ready, immediately — see the note on prebuffering
          // at the top of this file.
          if (!playingRef.current && audioQueueRef.current.length > 0) {
            void playQueue();
          }
        } catch (err) {
          console.error("TTS synthesis error:", err);
          // Only surface the banner if the voice has never actually spoken
          // this session -- that is a real, actionable failure. Once it HAS
          // spoken, a later single sentence failing (both the request and its
          // one retry) is a transient hiccup mid-conversation, not the voice
          // being broken; the generic "didn't load" banner said otherwise
          // while the rest of the answer kept being read underneath it, which
          // is confusing and wrong. Drop that one clip and keep going.
          if (!hasSpokenRef.current) {
            setError(err instanceof Error ? err.message : "Speech failed.");
          }
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

  const endTurn = useCallback(() => {
    // Nothing more will be queued this turn; if a tail clip is sitting idle
    // because playback had drained, start it.
    if (!playingRef.current && audioQueueRef.current.length > 0) void playQueue();
  }, [playQueue]);

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
      a.onplaying = null;
      a.pause();
      a.src = "";
    }
    liveAudioRef.current.clear();
    setIsPlaying(false);
  }, []);

  // A language switch mid-answer must not leave the previous voice talking.
  useEffect(() => stop, [language, stop]);

  return { speak, endTurn, stop, isReady, isPlaying, error };
}
