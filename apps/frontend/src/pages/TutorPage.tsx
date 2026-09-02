import { useEffect, useRef } from "react";
import type { SchoolClass, Subject } from "../types";
import type { TutorLanguage } from "../config/languages";
import { useTutorSession } from "../hooks/useTutorSession";
import { ChatBubble } from "../components/ChatBubble";
import { MicButton } from "../components/MicButton";
import { ErrorBanner } from "../components/ErrorBanner";
import { StopSpeechButton } from "../components/StopSpeechButton";
import { VoiceToggle } from "../components/VoiceToggle";
import { LanguageSelect } from "../components/LanguageSelect";

interface TutorPageProps {
  schoolClass: SchoolClass;
  subject: Subject;
  language: TutorLanguage;
  onLanguageChange: (code: string) => void;
}

const STAGE_CAPTION: Record<string, string> = {
  idle: "Tap the mic and ask a question",
  listening: "Listening — tap to send",
  thinking: "Thinking…",
  speaking: "Speaking the answer…",
  error: "Tap the mic and ask a question",
};

export function TutorPage({ schoolClass, subject, language, onLanguageChange }: TutorPageProps) {
  const {
    messages,
    stage,
    error,
    transcript,
    interimTranscript,
    isTranscribing,
    isVoiceReady,
    isModelWarm,
    voiceMissing,
    voiceLoading,
    voiceDownloadProgress,
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
  const micDisabled = !sttSupported || !isReady;

  // The offline speech models report a real percentage while streaming in; on a
  // cache hit there's no signal, so fall back to an indeterminate bar.
  const dl = sttLoading ? sttDownloadProgress : null;
  const isDownloading = !!dl && dl.total > 0 && dl.loaded > 0 && dl.loaded < dl.total;
  const prepPct = isDownloading
    ? Math.min(99, Math.round((dl!.loaded / dl!.total) * 100))
    : null;

  const vdl = voiceDownloadProgress;
  const voicePct =
    vdl && vdl.total > 0 && vdl.loaded > 0
      ? Math.min(99, Math.round((vdl.loaded / vdl.total) * 100))
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
          <span className="app-logo" aria-hidden="true">AI</span>
          <div className="app-titles">
            <span className="app-name">AI Tutor POC</span>
            <span className="app-context">
              {[schoolClass.name, subject.name].filter(Boolean).join(" · ") ||
                "Ask a question in any subject"}
            </span>
          </div>
        </div>
        <div className="app-bar-actions">
          <LanguageSelect
            code={language.code}
            onChange={onLanguageChange}
            disabled={stage === "thinking" || stage === "speaking"}
          />
          <VoiceToggle enabled={isVoiceEnabled} onToggle={toggleVoice} />
          <span className={`status-pill status-pill--${voiceStatus.tone}`}>
            <span className="status-dot" aria-hidden="true" />
            {voiceStatus.label}
          </span>
        </div>
      </header>

      <main className="screen tutor-screen">
        {!sttSupported && (
          <ErrorBanner
            message={
              language.stt.engine === "backend"
                ? "The offline speech model isn't ready. Re-run scripts/setup.ps1 and make sure the backend is running."
                : "This browser doesn't support speech recognition. Try Chrome or Edge."
            }
          />
        )}

        {sttSupported && isVoiceEnabled && voiceMissing && (
          <ErrorBanner
            message={`No offline ${language.name} voice is installed, so answers are read aloud with another voice. On Windows, add it under Settings → Time & Language → Speech, or turn the voice off.`}
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

        {voiceLoading && (
          <div className="voice-progress">
            <div className="voice-progress-header">
              <span>Preparing the {language.native} voice</span>
              <span>{voicePct !== null ? `${voicePct}%` : "…"}</span>
            </div>
            <div className="voice-progress-track">
              <div
                className={
                  voicePct !== null
                    ? "voice-progress-fill"
                    : "voice-progress-fill voice-progress-fill--indeterminate"
                }
                style={voicePct !== null ? { width: `${voicePct}%` } : undefined}
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
