import { useCallback, useEffect, useState } from "react";
import type { SchoolClass, Subject } from "./types";
import { TutorPage } from "./pages/TutorPage";
import { SetupPage } from "./pages/SetupPage";
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

type View = "tutor" | "setup";

/**
 * The view lives in the URL hash rather than in state alone.
 *
 * The desktop launcher opens a borderless window with no address bar and the
 * dev server hot-reloads on every edit; with state-only routing, both would
 * drop you back on the tutor mid-upload. A hash survives the reload and lets
 * the setup page be opened directly at #setup.
 */
function currentView(): View {
  return window.location.hash === "#setup" ? "setup" : "tutor";
}

function App() {
  const [langCode, setLangCode] = useState<string>(readStoredLanguage);
  const [view, setView] = useState<View>(currentView);

  const changeLanguage = useCallback((code: string) => {
    setLangCode(code);
    try {
      localStorage.setItem(LANG_STORAGE_KEY, code);
    } catch {
      // Private window / storage blocked — the choice just won't persist.
    }
  }, []);

  useEffect(() => {
    const onHashChange = () => setView(currentView());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  if (view === "setup") {
    return <SetupPage onBack={() => { window.location.hash = ""; }} />;
  }

  return (
    <TutorPage
      schoolClass={STATIC_CLASS}
      subject={STATIC_SUBJECT}
      language={languageByCode(langCode)}
      onLanguageChange={changeLanguage}
      onOpenSetup={() => { window.location.hash = "setup"; }}
    />
  );
}

export default App;
