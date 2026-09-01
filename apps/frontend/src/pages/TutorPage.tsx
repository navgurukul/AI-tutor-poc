import { useEffect, useRef } from "react";
import type { SchoolClass, Subject } from "../types";
import { useTutorSession } from "../hooks/useTutorSession";
import { ChatBubble } from "../components/ChatBubble";
import { MicButton } from "../components/MicButton";
import { ErrorBanner } from "../components/ErrorBanner";
import { StopSpeechButton } from "../components/StopSpeechButton";
import { VoiceToggle } from "../components/VoiceToggle";

interface TutorPageProps {
  schoolClass: SchoolClass;
  subject: Subject;
  /** Opens the textbook library. Omitted, the button is hidden. */
  onOpenSetup?: () => void;
}

const STAGE_CAPTION: Record<string, string> = {
  idle: "Tap the mic and ask a question",
  listening: "Listening — tap to stop",
  thinking: "Thinking…",
  speaking: "Speaking the answer…",
  error: "Tap the mic and ask a question",
};

export function TutorPage({ schoolClass, subject, onOpenSetup }: TutorPageProps) {
  const {
    messages,
    stage,
    error,
    transcript,
    interimTranscript,
    isVoiceReady,
    voiceDownloadProgress,
    isModelWarm,
    browserSupportsSpeechRecognition,
    isPlaying,
    isVoiceEnabled,
    startTurn,
    finishTurn,
    stopSpeaking,
    toggleVoice,
  } = useTutorSession({ subjectName: subject.name, level: schoolClass.name });

  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, interimTranscript]);

  // "Ready" = the Piper voice model has downloaded and the LLM warm-up has
  // settled. Until then the mic stays disabled.
  const isReady = isVoiceReady && isModelWarm;
  const micDisabled = !browserSupportsSpeechRecognition || !isReady;

  const progressPct =
    voiceDownloadProgress && voiceDownloadProgress.total > 0
      ? Math.min(
          100,
          Math.round((voiceDownloadProgress.loaded / voiceDownloadProgress.total) * 100),
        )
      : null;

  // Voice model first, then the LLM warm-up.
  const prepLabel = !isVoiceReady ? "Preparing voice model" : "Warming up the tutor model";
  const showDeterminate = !isVoiceReady && progressPct !== null;

  let voiceStatus: { label: string; tone: "ready" | "loading" | "error" };
  if (!browserSupportsSpeechRecognition) {
    voiceStatus = { label: "Mic unsupported", tone: "error" };
  } else if (isReady) {
    voiceStatus = { label: "Ready", tone: "ready" };
  } else {
    voiceStatus = {
      label: showDeterminate ? `${prepLabel} · ${progressPct}%` : `${prepLabel}…`,
      tone: "loading",
    };
  }

  return (
    <div className="app-shell">
      <header className="app-bar">
        <div className="app-brand">
          <span className="app-logo" aria-hidden="true">AI</span>
          <div className="app-titles">
            <span className="app-name">AI Tutor POC</span>
            <span className="app-context">
              {schoolClass.name} · {subject.name}
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
        {!browserSupportsSpeechRecognition && (
          <ErrorBanner message="This browser doesn't support speech recognition. Try Chrome or Edge." />
        )}

        {!isReady && browserSupportsSpeechRecognition && (
          <div className="voice-progress">
            <div className="voice-progress-header">
              <span>{prepLabel}</span>
              <span>{showDeterminate ? `${progressPct}%` : "…"}</span>
            </div>
            <div className="voice-progress-track">
              <div
                className={
                  showDeterminate
                    ? "voice-progress-fill"
                    : "voice-progress-fill voice-progress-fill--indeterminate"
                }
                style={showDeterminate ? { width: `${progressPct}%` } : undefined}
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
          {stage === "listening" && (interimTranscript || transcript) && (
            <div className="chat-bubble chat-bubble--user chat-bubble--interim">
              {transcript} {interimTranscript}
            </div>
          )}
        </div>

        <div className="tutor-controls">
          <MicButton
            stage={stage}
            disabled={micDisabled}
            onStart={startTurn}
            onFinish={finishTurn}
          />
          {isPlaying && <StopSpeechButton onStop={stopSpeaking} />}
          <p className="tutor-caption">
            {isPlaying ? "Speaking the answer…" : STAGE_CAPTION[stage]}
            {!isVoiceEnabled && stage === "idle" && !isPlaying && " · voice off"}
          </p>
        </div>
      </main>
    </div>
  );
}
