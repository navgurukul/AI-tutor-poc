import { LANGUAGES } from "../config/languages";

interface LanguageSelectProps {
  code: string;
  onChange: (code: string) => void;
  disabled?: boolean;
}

function GlobeIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.7 4 6.3 4 9s-1.5 6.3-4 9c-2.5-2.7-4-6.3-4-9s1.5-6.3 4-9Z" />
    </svg>
  );
}

/**
 * Picks the tutor's language — sets `profile.language` for the LLM and the
 * speech-recognition locale. A plain <select> so it stays keyboard- and
 * screen-reader-accessible.
 */
export function LanguageSelect({ code, onChange, disabled }: LanguageSelectProps) {
  return (
    <label className="lang-select" title="Tutor language">
      <GlobeIcon />
      <span className="lang-select-current">
        {LANGUAGES.find((l) => l.code === code)?.native ?? "English"}
      </span>
      <select
        value={code}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Tutor language"
      >
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>
            {l.native}
            {l.native !== l.name ? ` (${l.name})` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
