import { useEffect, useRef } from "react";
import type { SchoolClass, Subject } from "../types";
import { useTutorSession } from "../hooks/useTutorSession";
import { ChatBubble } from "../components/ChatBubble";
import { MicButton } from "../components/MicButton";
import { ErrorBanner } from "../components/ErrorBanner";

interface TutorPageProps {
  schoolClass: SchoolClass;
  subject: Subject;
}

const STAGE_CAPTION: Record<string, string> = {
  idle: "Tap the mic and ask a question",
  listening: "Listening — tap to stop",
  thinking: "Thinking…",
  speaking: "Speaking the answer…",
  error: "Tap the mic and ask a question",
};

export function TutorPage({ schoolClass, subject }: TutorPageProps) {
  const {
    messages,
    stage,
    error,
    transcript,
    interimTranscript,
    isVoiceReady,
    isVoiceLoading,
    voiceDownloadProgress,
    browserSupportsSpeechRecognition,
    startTurn,
    cancelTurn,
  } = useTutorSession({ subjectName: subject.name, level: schoolClass.name });

  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, interimTranscript]);

  const micDisabled = !browserSupportsSpeechRecognition || !isVoiceReady;
  const progressPct =
    voiceDownloadProgress && voiceDownloadProgress.total > 0
      ? Math.min(100, Math.round((voiceDownloadProgress.loaded / voiceDownloadProgress.total) * 100))
      : null;

  let voiceStatus: { label: string; tone: "ready" | "loading" | "error" };
  if (!browserSupportsSpeechRecognition) {
    voiceStatus = { label: "Mic unsupported", tone: "error" };
  } else if (isVoiceReady) {
    voiceStatus = { label: "Ready", tone: "ready" };
  } else {
    voiceStatus = { label: `Preparing voice${progressPct !== null ? ` · ${progressPct}%` : ""}`, tone: "loading" };
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
        <span className={`status-pill status-pill--${voiceStatus.tone}`}>
          <span className="status-dot" aria-hidden="true" />
          {voiceStatus.label}
        </span>
      </header>

      <main className="screen tutor-screen">
        {!browserSupportsSpeechRecognition && (
          <ErrorBanner message="This browser doesn't support speech recognition. Try Chrome or Edge." />
        )}

        {isVoiceLoading && !isVoiceReady && (
          <div className="voice-progress">
            <div className="voice-progress-header">
              <span>Preparing voice model</span>
              <span>{progressPct !== null ? `${progressPct}%` : "…"}</span>
            </div>
            <div className="voice-progress-track">
              <div
                className="voice-progress-fill"
                style={{ width: `${progressPct ?? 6}%` }}
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
            onCancel={cancelTurn}
          />
          <p className="tutor-caption">{STAGE_CAPTION[stage]}</p>
        </div>
      </main>
    </div>
  );
}
