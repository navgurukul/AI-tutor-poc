import { useCallback, useState } from "react";
import type { SchoolClass, Subject } from "./types";
import { TutorPage } from "./pages/TutorPage";
import { DEFAULT_LANGUAGE, languageByCode } from "./config/languages";

// Class/subject selection is removed for now. Left blank on purpose: a fixed
// "Class 6 · Mathematics" persona made the tutor force every question (including
// English/Hindi ones that aren't school maths) into 6th-grade-maths framing.
// Blank names => the backend skips the subject/level lines and answers generally.
const STATIC_CLASS: SchoolClass = { id: "general", name: "" };
const STATIC_SUBJECT: Subject = { id: "general", name: "" };

const LANG_STORAGE_KEY = "tutor.language";

function readStoredLanguage(): string {
  try {
    return localStorage.getItem(LANG_STORAGE_KEY) ?? DEFAULT_LANGUAGE.code;
  } catch {
    return DEFAULT_LANGUAGE.code;
  }
}

function App() {
  const [langCode, setLangCode] = useState<string>(readStoredLanguage);

  const changeLanguage = useCallback((code: string) => {
    setLangCode(code);
    try {
      localStorage.setItem(LANG_STORAGE_KEY, code);
    } catch {
      // Private window / storage blocked — the choice just won't persist.
    }
  }, []);

  return (
    <TutorPage
      schoolClass={STATIC_CLASS}
      subject={STATIC_SUBJECT}
      language={languageByCode(langCode)}
      onLanguageChange={changeLanguage}
    />
  );
}

export default App;
