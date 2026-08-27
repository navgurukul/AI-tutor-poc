interface VoiceToggleProps {
  enabled: boolean;
  onToggle: () => void;
}

function SpeakerOnIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="4 9 8 9 12 5 12 19 8 15 4 15" fill="currentColor" stroke="none" />
      <path d="M16 8a5 5 0 0 1 0 8" />
      <path d="M19 5a9 9 0 0 1 0 14" />
    </svg>
  );
}

function SpeakerOffIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="4 9 8 9 12 5 12 19 8 15 4 15" fill="currentColor" stroke="none" />
      <line x1="16" y1="9" x2="21" y2="14" />
      <line x1="21" y1="9" x2="16" y2="14" />
    </svg>
  );
}

/**
 * Turns spoken answers on and off for the whole session. Distinct from the
 * "Stop audio" button, which only interrupts the reply being spoken right now.
 */
export function VoiceToggle({ enabled, onToggle }: VoiceToggleProps) {
  return (
    <button
      type="button"
      className={`voice-toggle${enabled ? "" : " voice-toggle--off"}`}
      onClick={onToggle}
      aria-pressed={enabled}
      title={enabled ? "Turn off spoken answers" : "Turn on spoken answers"}
    >
      {enabled ? <SpeakerOnIcon /> : <SpeakerOffIcon />}
      <span>{enabled ? "Voice on" : "Voice off"}</span>
    </button>
  );
}
