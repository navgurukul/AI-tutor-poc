import { useEffect, useRef } from "react";
import type { SchoolClass, Subject } from "../types";
import type { TutorLanguage } from "../config/languages";
import { useTutorSession } from "../hooks/useTutorSession";
import { ChatBubble } from "../components/ChatBubble";
import { MicButton } from "../components/MicButton";
import { ErrorBanner } from "../components/ErrorBanner";
import { StopSpeechButton } from "../components/StopSpeechButton";
import { VoiceToggle } from "../components/VoiceToggle";

interface TutorPageProps {
  schoolClass: SchoolClass;
  subject: Subject;
  /**
   * Displayed, not editable. Language, class and subject are chosen ONLY in the
   * lobby; this page shows them and offers Back.
   *
   * This header used to carry a language picker, and it quietly behaved
   * differently from the lobby. The lobby re-primes and hands over a warm
   * session, so the next question costs ~1.8s; switching here warmed in the
   * background and left the next question paying full price. Worse, it changed
   * the persona mid-session, which broke the cached prompt prefix and left the
   * replayed history in the previous language. One route in means one
   * behaviour.
   */
  language: TutorLanguage;
  /**
   * Session the lobby already warmed. Continuing it is what makes the first
   * question fast: a question in a NEW session re-prefills the whole persona
   * and pinned textbook (19.5s measured), while one that continues the primed
   * session extends a cache that already holds them (1.8s).
   */
  primedSessionId?: string;
  /**
   * Back to the lobby, where language, class and subject are chosen.
   * Omitted, the button is hidden.
   */
  onBack?: () => void;
  /** Opens the textbook library. Omitted, the button is hidden. */
  onOpenSetup?: () => void;
}

const STAGE_CAPTION: Record<string, string> = {
  idle: "Tap the mic to speak, or type — then check it and Send",
  listening: "Listening — tap to stop",
  thinking: "Thinking…",
  speaking: "Speaking the answer…",
  error: "Tap the mic to speak, or type — then check it and Send",
};

export function TutorPage({
  schoolClass,
  subject,
  language,
  primedSessionId,
  onBack,
  onOpenSetup,
}: TutorPageProps) {
  const {
    messages,
    stage,
    error,
    draft,
    setDraft,
    sendDraft,
    transcript,
    interimTranscript,
    isTranscribing,
    isVoiceReady,
    isModelWarm,
    voiceError,
    sttSupported,
    sttLoading,
    sttDownloadProgress,
    isPlaying,
    isVoiceEnabled,
    startTurn,
    finishTurn,
    stopSpeaking,
    toggleVoice,
  } = useTutorSession({
    subjectName: subject.name,
    level: schoolClass.name,
    language,
    primedSessionId,
  });

  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, interimTranscript, isTranscribing]);

  // "Ready" = the LLM warm-up has settled, the STT engine for this language is
  // prepared (instant for the browser recognizer; a one-time model load the
  // first time an offline language is picked), and a voice has been selected
  // (near-instant — the OS synthesizer needs no download).
  const isReady = isModelWarm && !sttLoading && isVoiceReady;
  // The mic doesn't wait on the model. Speaking, and transcribing what was
  // said, both finish before the LLM is asked anything — so blocking the button
  // on the warm-up just spends that time on a disabled control instead of on
  // the question. Only the recognizer has to be there to press it; the status
  // pill still reports the warm-up, and a question asked early simply waits.
  const micDisabled = !sttSupported || sttLoading;
  // Lock the question box while the mic is capturing (its transcript lands here
  // when it closes) and while the tutor is mid-turn.
  const inputLocked =
    stage === "listening" || stage === "thinking" || stage === "speaking";

  // The offline speech models report a real percentage while streaming in; on a
  // cache hit there's no signal, so fall back to an indeterminate bar.
  const dl = sttLoading ? sttDownloadProgress : null;
  const isDownloading = !!dl && dl.total > 0 && dl.loaded > 0 && dl.loaded < dl.total;
  const prepPct = isDownloading
    ? Math.min(99, Math.round((dl!.loaded / dl!.total) * 100))
    : null;

  const prepLabel = sttLoading
    ? isDownloading
      ? "Downloading speech model"
      : "Preparing speech model"
    : `Preparing the ${language.native} tutor`;

  let voiceStatus: { label: string; tone: "ready" | "loading" | "error" };
  if (!sttSupported) {
    voiceStatus = { label: "Speech unavailable", tone: "error" };
  } else if (isReady) {
    voiceStatus = { label: "Ready", tone: "ready" };
  } else {
    voiceStatus = {
      label: prepPct !== null ? `${prepLabel} · ${prepPct}%` : `${prepLabel}…`,
      tone: "loading",
    };
  }

  const pendingSpeech = interimTranscript || transcript;

  return (
    <div className="app-shell">
      <header className="app-bar">
        <div className="app-brand">
          {onBack && (
            <button
              className="appbar__back"
              type="button"
              onClick={onBack}
              title="Change language, class or subject"
              aria-label="Back to setup"
            >
              ‹
            </button>
          )}
          <span className="app-logo" aria-hidden="true">AI</span>
          <div className="app-titles">
            <span className="app-name">AI Tutor POC</span>
            <span className="app-context">
              {[language.native, schoolClass.name, subject.name]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </div>
        </div>
        <div className="app-bar-actions">
          {onOpenSetup && (
            <button className="appbar__setup" type="button" onClick={onOpenSetup}>
              Library
            </button>
          )}
          <VoiceToggle enabled={isVoiceEnabled} onToggle={toggleVoice} />
          <span className={`status-pill status-pill--${voiceStatus.tone}`}>
            <span className="status-dot" aria-hidden="true" />
            {voiceStatus.label}
          </span>
        </div>
      </header>

      <main className="screen tutor-screen">
        {!sttSupported && (
          <ErrorBanner message="The offline speech model isn't ready. Re-run scripts/setup.ps1 and make sure the backend is running." />
        )}

        {sttSupported && isVoiceEnabled && voiceError && (
          <ErrorBanner
            message={`The ${language.name} voice didn't load, so answers won't be read aloud. Reload the page to retry, or turn the voice off.`}
          />
        )}

        {!isReady && sttSupported && (
          <div className="voice-progress">
            <div className="voice-progress-header">
              <span>{prepLabel}</span>
              <span>{prepPct !== null ? `${prepPct}%` : "…"}</span>
            </div>
            <div className="voice-progress-track">
              <div
                className={
                  prepPct !== null
                    ? "voice-progress-fill"
                    : "voice-progress-fill voice-progress-fill--indeterminate"
                }
                style={prepPct !== null ? { width: `${prepPct}%` } : undefined}
              />
            </div>
          </div>
        )}


        {error && <ErrorBanner message={error} />}

        <div className="chat-log" ref={logRef}>
          {messages.length === 0 && (
            <div className="chat-empty">
              <span className="chat-empty-icon" aria-hidden="true">💬</span>
              <p>Tap the mic and ask your tutor a question.</p>
            </div>
          )}
          {messages.map((m) => (
            <ChatBubble key={m.id} {...m} />
          ))}
          {/* The recognized speech shows straight in the chat as a faint user
              bubble — live for English, once decoded for the offline engine —
              then becomes the real message when it's sent. */}
          {stage === "listening" && pendingSpeech && (
            <div className="chat-bubble chat-bubble--user chat-bubble--interim" dir="auto">
              {transcript} {interimTranscript}
            </div>
          )}
          {isTranscribing && (
            <div className="chat-bubble chat-bubble--user chat-bubble--interim">…</div>
          )}
        </div>

        <div className="tutor-controls">
          <form
            className="tutor-input"
            onSubmit={(e) => {
              e.preventDefault();
              sendDraft();
            }}
          >
            <textarea
              className="tutor-input-field"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendDraft();
                }
              }}
              placeholder="Speak or type your question, then check it here before sending…"
              rows={2}
              dir="auto"
              disabled={inputLocked}
            />
            <button
              type="submit"
              className="tutor-send"
              disabled={inputLocked || !draft.trim()}
            >
              Send
            </button>
          </form>
          <MicButton
            stage={stage}
            disabled={micDisabled}
            onStart={startTurn}
            onFinish={finishTurn}
          />
          {isPlaying && <StopSpeechButton onStop={stopSpeaking} />}
          <p className="tutor-caption">
            {isTranscribing
              ? "Transcribing…"
              : isPlaying
                ? "Speaking the answer…"
                : STAGE_CAPTION[stage]}
            {!isVoiceEnabled && stage === "idle" && !isPlaying && !isTranscribing && " · voice off"}
          </p>
        </div>
      </main>
    </div>
  );
}
