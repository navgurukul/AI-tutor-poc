import { useCallback, useEffect, useState } from "react";
import { TutorPage } from "./pages/TutorPage";
import { SetupPage } from "./pages/SetupPage";
import { StartPage } from "./pages/StartPage";
import { DEFAULT_LANGUAGE, languageByCode } from "./config/languages";
import {
  classById,
  subjectById,
  subjectsFromCoverage,
  type Coverage,
} from "./config/curriculum";
import { fetchLibraryStatus } from "./services/library";

// Class and subject are chosen in the lobby again (2026-09-09), having been
// fixed-and-blank before that. The original reason for removing them still
// stands and is worth keeping in view: a hard-coded "Class 6 · Mathematics"
// persona pushed every question, including Hindi grammar ones, into
// sixth-grade-maths framing. What makes it safe to reintroduce is that
// "Any / general" is the default and maps to an empty name, which the backend
// treats as "omit that line" -- so the narrowing only happens when a student
// asks for it.
const LANG_STORAGE_KEY = "tutor.language";
const CLASS_STORAGE_KEY = "tutor.class";
const SUBJECT_STORAGE_KEY = "tutor.subject";

function readStored(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    // Private window / storage blocked — the choice just won't persist.
    return fallback;
  }
}

function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // As above: losing the preference is acceptable, crashing is not.
  }
}

type View = "start" | "tutor" | "setup";

/**
 * The view lives in the URL hash rather than in state alone.
 *
 * The desktop launcher opens a borderless window with no address bar and the
 * dev server hot-reloads on every edit; with state-only routing, both would
 * drop you back on the tutor mid-upload. A hash survives the reload and lets
 * the setup page be opened directly at #setup.
 */
function currentView(): View {
  if (window.location.hash === "#setup") return "setup";
  // #tutor is reached by pressing Start, never by landing. The default is the
  // lobby: the models and the pinned textbook have to be loaded before the
  // first question, and the only choice is whether the student waits for that
  // here (where waiting is expected) or on their first question (where it
  // reads as a broken tutor). Measured 2026-09-09: 18.5s on a cold first turn
  // against 3.6-3.9s once warm.
  if (window.location.hash === "#tutor") return "tutor";
  return "start";
}

function App() {
  const [langCode, setLangCode] = useState<string>(() =>
    readStored(LANG_STORAGE_KEY, DEFAULT_LANGUAGE.code),
  );
  const [classId, setClassId] = useState<string>(() =>
    readStored(CLASS_STORAGE_KEY, "general"),
  );
  const [subjectId, setSubjectId] = useState<string>(() =>
    readStored(SUBJECT_STORAGE_KEY, "general"),
  );
  // What the library actually holds. The lobby's dropdowns are built from this
  // so it can only offer combinations there is a textbook for.
  const [coverage, setCoverage] = useState<Coverage[]>([]);
  const [view, setView] = useState<View>(currentView);
  // The session the lobby warmed. The tutor continues it rather than opening a
  // new one: measured 2026-09-09, a first question that continues the primed
  // session prefills in 1.8s where the same question in a fresh session takes
  // 19.5s. Empty when the tutor was reached without going through the lobby.
  const [primedSessionId, setPrimedSessionId] = useState("");

  // All three live here rather than in the lobby so the tutor page builds its
  // profile from the same values the warm-up used. The persona embeds language,
  // class and subject, and the persona is the cached prefix -- if the two pages
  // disagree by so much as a word, the lobby primes a prefix the first question
  // cannot reuse and the student waits twice.
  const changeLanguage = useCallback((code: string) => {
    setLangCode(code);
    writeStored(LANG_STORAGE_KEY, code);
  }, []);

  const changeClass = useCallback(
    (id: string) => {
      setClassId(id);
      writeStored(CLASS_STORAGE_KEY, id);
      // Classes hold different subjects. Moving to one that has no book for the
      // currently selected subject would leave the dropdown showing a value it
      // no longer contains, and — worse — send that stale subject into the
      // persona and look for a book that isn't there. Fall back to "general".
      setSubjectId((current) => {
        if (subjectsFromCoverage(coverage, id).some((s) => s.id === current)) {
          return current;
        }
        writeStored(SUBJECT_STORAGE_KEY, "general");
        return "general";
      });
    },
    [coverage],
  );

  const changeSubject = useCallback((id: string) => {
    setSubjectId(id);
    writeStored(SUBJECT_STORAGE_KEY, id);
  }, []);

  const schoolClass = classById(classId);
  const subject = subjectById(subjectId, coverage);
  const language = languageByCode(langCode);

  // Refreshed whenever the lobby is shown, so a textbook added on the library
  // page appears in the dropdowns without a reload.
  useEffect(() => {
    if (view !== "start") return;
    let active = true;
    void fetchLibraryStatus()
      .then((s) => {
        if (active) setCoverage(s.coverage ?? []);
      })
      .catch(() => {
        // The lobby still works with an empty list — it falls back to
        // "Any / general", which pins nothing and answers unaided.
      });
    return () => {
      active = false;
    };
  }, [view]);

  useEffect(() => {
    const onHashChange = () => setView(currentView());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  // Send anyone who reaches #tutor without a primed session back to the lobby.
  // Happens on a reload (Vite hot-reloads on every edit), a bookmark, or the
  // desktop window restoring its last hash. The chat would still work, but the
  // first question re-prefills the persona and pinned textbook from cold — 22s
  // measured 2026-09-10, against ~2s when the lobby's session is handed over.
  // In an effect rather than during render: navigating is a side effect, and
  // StrictMode renders twice.
  useEffect(() => {
    if (view === "tutor" && !primedSessionId) window.location.hash = "";
  }, [view, primedSessionId]);

  if (view === "setup") {
    return <SetupPage onBack={() => { window.location.hash = ""; }} />;
  }

  // Landing on #tutor without a primed session means the lobby was skipped —
  // a reload (Vite hot-reloads on every edit), a bookmark, or the desktop
  // window restoring its last hash. The chat works, but the first question then
  // re-prefills the whole persona and pinned textbook from cold: 26s measured
  // on 2026-09-10, against 1.9s when the lobby's session is handed over. Send
  // them through the lobby instead; it re-primes in the background and the
  // difference is invisible once warm.
  if (view === "tutor" && !primedSessionId) return null;

  if (view === "start") {
    return (
      <StartPage
        schoolClass={schoolClass}
        subject={subject}
        language={language}
        coverage={coverage}
        onLanguageChange={changeLanguage}
        onClassChange={changeClass}
        onSubjectChange={changeSubject}
        onStart={(sessionId) => {
          setPrimedSessionId(sessionId);
          window.location.hash = "tutor";
        }}
        onOpenLibrary={() => { window.location.hash = "setup"; }}
      />
    );
  }

  return (
    <TutorPage
      schoolClass={schoolClass}
      subject={subject}
      language={language}
      primedSessionId={primedSessionId}
      onBack={() => {
        // Drop the primed session on the way out. Returning to the lobby always
        // re-primes, and a stale id here would let the tutor continue a session
        // whose persona may no longer match what was just chosen.
        setPrimedSessionId("");
        window.location.hash = "";
      }}
      onOpenSetup={() => { window.location.hash = "setup"; }}
    />
  );
}

export default App;
