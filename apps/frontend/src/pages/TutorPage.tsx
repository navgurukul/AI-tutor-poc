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

  // "Ready" = the LLM warm-up has settled (the browser voice is available
  // instantly, no download). Until then the first question pays the cold start.
  const isReady = isVoiceReady && isModelWarm;
  const micDisabled = !browserSupportsSpeechRecognition || !isReady;

  let voiceStatus: { label: string; tone: "ready" | "loading" | "error" };
  if (!browserSupportsSpeechRecognition) {
    voiceStatus = { label: "Mic unsupported", tone: "error" };
  } else if (isReady) {
    voiceStatus = { label: "Ready", tone: "ready" };
  } else {
    voiceStatus = { label: "Warming up the tutor…", tone: "loading" };
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
              <span>Warming up the tutor model</span>
              <span>…</span>
            </div>
            <div className="voice-progress-track">
              <div className="voice-progress-fill voice-progress-fill--indeterminate" />
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
