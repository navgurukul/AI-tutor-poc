interface StopSpeechButtonProps {
  onStop: () => void;
}

function StopSquareIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

/** Shown only while the tutor is speaking, so it never sits there inert. */
export function StopSpeechButton({ onStop }: StopSpeechButtonProps) {
  return (
    <button type="button" className="stop-speech-button" onClick={onStop}>
      <StopSquareIcon />
      <span>Stop audio</span>
    </button>
  );
}
