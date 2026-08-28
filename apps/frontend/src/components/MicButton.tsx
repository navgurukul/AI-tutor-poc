import type { ComponentType } from "react";
import type { TutorStage } from "../hooks/useTutorSession";

interface MicButtonProps {
  stage: TutorStage;
  disabled: boolean;
  onStart: () => void;
  onFinish: () => void;
}

const LABELS: Record<TutorStage, string> = {
  idle: "Speak",
  listening: "Send",
  thinking: "Thinking…",
  speaking: "Speaking…",
  error: "Speak",
};

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
      <rect x="5" y="5" width="14" height="14" rx="3" />
    </svg>
  );
}

function SpeakerIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="4 9 8 9 12 5 12 19 8 15 4 15" fill="currentColor" stroke="none" />
      <path d="M16 8a5 5 0 0 1 0 8" />
      <path d="M19 5a9 9 0 0 1 0 14" />
    </svg>
  );
}

const ICONS: Record<TutorStage, ComponentType> = {
  idle: MicIcon,
  listening: StopIcon,
  thinking: () => <span className="mic-button-spinner" aria-hidden="true" />,
  speaking: SpeakerIcon,
  error: MicIcon,
};

export function MicButton({ stage, disabled, onStart, onFinish }: MicButtonProps) {
  const isListening = stage === "listening";
  const isBusy = stage === "thinking" || stage === "speaking";
  const Icon = ICONS[stage];

  return (
    <div className="mic-wrap">
      {isListening && <span className="mic-pulse" aria-hidden="true" />}
      <button
        type="button"
        className={`mic-button mic-button--${stage}`}
        disabled={disabled || isBusy}
        onClick={isListening ? onFinish : onStart}
      >
        <Icon />
        <span>{LABELS[stage]}</span>
      </button>
    </div>
  );
}
