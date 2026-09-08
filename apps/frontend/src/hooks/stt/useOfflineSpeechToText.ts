/**
 * Speech-to-text that actually works offline.
 *
 * `react-sts-hooks`' useSpeechToText wraps the Web Speech API but never sets
 * `processLocally`, so Chrome streams every utterance to Google's servers.
 * On a school laptop with no internet that fails outright -- the recogniser
 * reports `network` and nothing is transcribed, which is exactly what a device
 * sold as "works offline" must not do.
 *
 * Chrome 138+ can run recognition on-device instead, but it takes two steps
 * that have to happen in order:
 *
 *   1. the SODA language pack must be present -- `SpeechRecognition.install()`
 *      downloads it once, into the Chrome *installation* rather than the
 *      profile, so it survives a new --profile-directory;
 *   2. `recognition.processLocally = true` must be set on each recogniser, or
 *      Chrome keeps using the network path even with the model sitting on disk.
 *
 * This hook does both, and degrades honestly: where on-device is unavailable it
 * still works online, and says so through `isOnDevice` rather than pretending.
 *
 * Drop-in for useSpeechToText -- same options, same return shape, plus three
 * fields the provisioning flow needs.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type OnDeviceStatus =
  | "unknown"        // not probed yet
  | "unsupported"    // no Web Speech API, or Chrome older than 138
  | "unavailable"    // this build/platform cannot do on-device for this language
  | "downloadable"   // supported, pack not fetched yet -- needs one online run
  | "downloading"
  | "available";     // ready; recognition stays on the machine

export interface UseOfflineSpeechToTextOptions {
  /** BCP 47 tag, e.g. 'en-US'. */
  lang: string;
  continuous: boolean;
  /** Milliseconds of silence before recognition stops itself. */
  silenceTimeout?: number;
  /**
   * Fetch the language pack automatically when it is missing and the machine
   * is online. On by default: a device is typically provisioned with a network
   * once, and that is the only moment the download can happen. It is a ~50 MB
   * one-off, so it never repeats.
   */
  autoInstall?: boolean;
}

export interface UseOfflineSpeechToTextReturn {
  isListening: boolean;
  transcript: string;
  interimTranscript: string;
  startListening: () => void;
  stopListening: () => void;
  resetTranscript: () => void;
  error: string | null;
  browserSupportsSpeechRecognition: boolean;
  /** True once recognition is running on the machine rather than via Google. */
  isOnDevice: boolean;
  onDeviceStatus: OnDeviceStatus;
  /** Fetch the pack on demand (the Library/setup screen can offer this). */
  installLanguagePack: () => Promise<boolean>;
}

type SRConstructor = {
  new (): SpeechRecognitionLike;
  available?: (opts: { langs: string[]; processLocally?: boolean }) => Promise<string>;
  install?: (opts: { langs: string[] }) => Promise<boolean>;
};

interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  processLocally?: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: any) => void) | null;
  onerror: ((e: any) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

function getSR(): SRConstructor | null {
  if (typeof window === "undefined") return null;
  return ((window as any).SpeechRecognition ||
    (window as any).webkitSpeechRecognition ||
    null) as SRConstructor | null;
}

/** Error codes are terse and land in front of a student, so translate them. */
function describe(code: string, onDevice: boolean): string {
  switch (code) {
    case "network":
      return onDevice
        ? "Speech recognition failed. Please try again."
        : "Speech needs the internet on this device. The offline voice pack is not installed yet.";
    case "not-allowed":
    case "service-not-allowed":
      return "Microphone access is blocked. Allow the microphone and try again.";
    case "audio-capture":
      return "No microphone was found. Check that one is connected and not muted.";
    case "no-speech":
      return "I did not hear anything. Try speaking a little louder.";
    case "aborted":
      return "";
    default:
      return `Speech recognition error: ${code}`;
  }
}

export function useOfflineSpeechToText({
  lang,
  continuous,
  silenceTimeout = 1000,
  autoInstall = true,
}: UseOfflineSpeechToTextOptions): UseOfflineSpeechToTextReturn {
  const SR = getSR();
  const supported = !!SR;

  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<OnDeviceStatus>("unknown");

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const silenceTimerRef = useRef<number | null>(null);
  // Read inside event handlers, which close over their first render otherwise.
  const statusRef = useRef<OnDeviceStatus>("unknown");
  const manualStopRef = useRef(false);
  // One download attempt per session: retrying on every click would queue
  // several 50 MB fetches on a slow link.
  const installStartedRef = useRef(false);

  const setStatusBoth = useCallback((s: OnDeviceStatus) => {
    statusRef.current = s;
    setStatus(s);
  }, []);

  // --- probe, and fetch the pack if this is the one online moment we get ---
  useEffect(() => {
    let cancelled = false;

    (async () => {
      if (!SR) return setStatusBoth("unsupported");
      if (typeof SR.available !== "function") return setStatusBoth("unsupported");

      try {
        const state = (await SR.available({ langs: [lang], processLocally: true })) as OnDeviceStatus;
        if (cancelled) return;
        setStatusBoth(state);
        // Logged deliberately: on a device this is the difference between
        // speech that survives a Wi-Fi drop and speech that dies with it, and
        // it is otherwise invisible until the network is already gone.
        console.info(
          `[stt] ${lang} on-device: ${state}` +
            (state === "available"
              ? " - recognition stays on this machine"
              : state === "downloadable"
                ? " - NOT installed; speech needs the internet until the pack downloads"
                : state === "unavailable"
                  ? " - this Chrome build cannot run en-US on-device"
                  : ""),
        );
        // Deliberately no install() here. Chrome requires transient user
        // activation before it will start a download this size, and a mount
        // effect has none -- install() then returns false with no error, which
        // looks exactly like "this machine cannot do on-device speech". The
        // download is kicked off from startListening() instead, which always
        // runs inside the click on Speak.
      } catch {
        // Probing must never break dictation: fall through to the online path.
        if (!cancelled) setStatusBoth("unavailable");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [SR, lang, setStatusBoth]);

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current !== null) {
      window.clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  }, []);

  const armSilenceTimer = useCallback(() => {
    clearSilenceTimer();
    if (!silenceTimeout) return;
    silenceTimerRef.current = window.setTimeout(() => {
      manualStopRef.current = true;
      recognitionRef.current?.stop();
    }, silenceTimeout);
  }, [clearSilenceTimer, silenceTimeout]);

  const stopListening = useCallback(() => {
    manualStopRef.current = true;
    clearSilenceTimer();
    recognitionRef.current?.stop();
  }, [clearSilenceTimer]);

  const startListening = useCallback(() => {
    if (!SR || isListening) return;
    setError(null);
    setInterimTranscript("");
    manualStopRef.current = false;

    // This call is inside the user's click on Speak, which is the only context
    // Chrome will accept for the language-pack download. Fire and forget: the
    // pack is ~50 MB, so this turn still goes through the network path and the
    // *next* one is on-device. Waiting here would stall the button for minutes.
    if (
      statusRef.current === "downloadable" &&
      autoInstall &&
      navigator.onLine &&
      SR.install &&
      !installStartedRef.current
    ) {
      installStartedRef.current = true;
      setStatusBoth("downloading");
      SR.install({ langs: [lang] })
        .then(async (ok) => {
          const after = (await SR.available!({
            langs: [lang],
            processLocally: true,
          })) as OnDeviceStatus;
          setStatusBoth(after);
          if (!ok && after !== "available") installStartedRef.current = false;
        })
        .catch(() => {
          installStartedRef.current = false;
          setStatusBoth("downloadable");
        });
    }

    let rec: SpeechRecognitionLike;
    try {
      rec = new SR();
    } catch {
      setError("Speech recognition could not start on this device.");
      return;
    }

    rec.lang = lang;
    rec.continuous = continuous;
    rec.interimResults = true;
    rec.maxAlternatives = 1;

    // The line this hook exists for. Only claimed when the pack is actually
    // present -- asserting it otherwise makes Chrome refuse to start at all.
    if (statusRef.current === "available") {
      try {
        rec.processLocally = true;
      } catch {
        /* older build: fall back to the network path */
      }
    }

    rec.onstart = () => {
      setIsListening(true);
      console.info(
        `[stt] listening (${lang}, ${statusRef.current === "available" ? "on-device" : "network"})`,
      );
      // Deliberately NOT arming the silence timer here. silenceTimeout means
      // "stop once the speaker has paused this long", not "stop this long
      // after the button was pressed" -- arming it on start gives the student
      // one second to begin talking and then cuts them off, which looks
      // exactly like the microphone not working. The timer is armed by the
      // first result instead; until then Chrome's own no-speech timeout is
      // the right backstop, and it reports honestly.
    };

    rec.onresult = (event: any) => {
      let finalText = "";
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) finalText += result[0].transcript;
        else interim += result[0].transcript;
      }
      if (finalText) {
        console.info(`[stt] heard: "${finalText.trim()}"`);
        setTranscript((prev) => (prev ? `${prev} ${finalText}`.trim() : finalText.trim()));
      }
      setInterimTranscript(interim);
      // First result arms the timer; every later one restarts it, so the clock
      // only ever measures a pause *between* words.
      armSilenceTimer();
    };

    rec.onerror = (event: any) => {
      const code = String(event?.error ?? "unknown");
      console.warn(`[stt] error: ${code}`);
      // A silence-triggered stop surfaces as no-speech/aborted; that is the
      // hook working, not a fault worth showing a student.
      if (manualStopRef.current && (code === "no-speech" || code === "aborted")) return;
      const message = describe(code, statusRef.current === "available");
      if (message) setError(message);
    };

    rec.onend = () => {
      console.info("[stt] stopped");
      clearSilenceTimer();
      setIsListening(false);
      setInterimTranscript("");
      recognitionRef.current = null;
    };

    recognitionRef.current = rec;
    try {
      rec.start();
    } catch {
      setError("Speech recognition could not start. Is the microphone already in use?");
      recognitionRef.current = null;
    }
  }, [SR, lang, continuous, isListening, autoInstall, armSilenceTimer, clearSilenceTimer, setStatusBoth]);

  const resetTranscript = useCallback(() => {
    setTranscript("");
    setInterimTranscript("");
  }, []);

  /**
   * Explicit download, for a setup screen. MUST be called from a click or
   * other user gesture -- Chrome refuses the download without one and returns
   * false rather than throwing.
   */
  const installLanguagePack = useCallback(async () => {
    if (!SR?.install) return false;
    installStartedRef.current = true;
    try {
      setStatusBoth("downloading");
      const ok = await SR.install({ langs: [lang] });
      const after = (await SR.available!({ langs: [lang], processLocally: true })) as OnDeviceStatus;
      setStatusBoth(after);
      return ok;
    } catch {
      setStatusBoth("downloadable");
      return false;
    }
  }, [SR, lang, setStatusBoth]);

  // Recognition holds the microphone; leaving it open across an unmount keeps
  // the OS capture indicator lit and blocks the next start().
  useEffect(() => {
    return () => {
      clearSilenceTimer();
      recognitionRef.current?.abort();
      recognitionRef.current = null;
    };
  }, [clearSilenceTimer]);

  return {
    isListening,
    transcript,
    interimTranscript,
    startListening,
    stopListening,
    resetTranscript,
    error,
    browserSupportsSpeechRecognition: supported,
    isOnDevice: status === "available",
    onDeviceStatus: status,
    installLanguagePack,
  };
}
