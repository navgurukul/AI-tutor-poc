import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Thin wrapper over the browser's built-in `speechSynthesis` (Web Speech API).
 *
 * Chosen over WASM Piper for the streamed tutor answer: the OS synthesizes
 * faster than real time, so the first sentence is audible in well under a second
 * and queued sentences play back-to-back with no gaps — on a low-end CPU where
 * Piper falls behind and stutters. On Windows/macOS the voices are local, so it
 * still works offline. Trade-off: the system voice is less natural than Piper's.
 */
export interface SpeechSynthesisApi {
  /** Queue a phrase. The browser plays queued phrases in order, gaplessly. */
  speak: (text: string) => void;
  /** Stop the current phrase and clear the queue. */
  cancel: () => void;
  /** False when the browser has no speechSynthesis at all (voice is then a no-op). */
  isSupported: boolean;
  /** True once a usable voice is available — effectively immediate. */
  isReady: boolean;
  /** True between the first phrase starting and the last one ending. */
  isSpeaking: boolean;
}

export function useSpeechSynthesis(lang = "en-US"): SpeechSynthesisApi {
  const isSupported =
    typeof window !== "undefined" && "speechSynthesis" in window;

  const [isReady, setIsReady] = useState(!isSupported);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);

  useEffect(() => {
    if (!isSupported) return;
    const synth = window.speechSynthesis;

    const pickVoice = () => {
      const voices = synth.getVoices();
      if (!voices.length) return;
      const wanted = lang.slice(0, 2).toLowerCase();
      const matches = voices.filter((v) =>
        (v.lang || "").toLowerCase().startsWith(wanted),
      );
      // Prefer a local (offline) voice in the requested language.
      voiceRef.current =
        matches.find((v) => v.localService) ??
        matches[0] ??
        voices.find((v) => v.localService) ??
        voices[0] ??
        null;
      setIsReady(true);
    };

    pickVoice();
    // Chrome populates getVoices() asynchronously on first use.
    synth.addEventListener("voiceschanged", pickVoice);
    // ...but if it never fires, speak() still works with the browser default —
    // don't leave the mic gated on it forever.
    const fallback = window.setTimeout(() => setIsReady(true), 2000);
    return () => {
      synth.removeEventListener("voiceschanged", pickVoice);
      window.clearTimeout(fallback);
    };
  }, [isSupported, lang]);

  const speak = useCallback(
    (text: string) => {
      if (!isSupported) return;
      const phrase = text.trim();
      if (!phrase) return;
      const synth = window.speechSynthesis;
      const utterance = new SpeechSynthesisUtterance(phrase);
      utterance.lang = lang;
      if (voiceRef.current) utterance.voice = voiceRef.current;
      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(synth.speaking);
      utterance.onerror = () => setIsSpeaking(synth.speaking);
      synth.speak(utterance);
    },
    [isSupported, lang],
  );

  const cancel = useCallback(() => {
    if (!isSupported) return;
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }, [isSupported]);

  return { speak, cancel, isSupported, isReady, isSpeaking };
}
