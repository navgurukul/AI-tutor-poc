import { useEffect, useState } from "react";
import type { SchoolClass, Subject } from "./types";
import { TutorPage } from "./pages/TutorPage";
import { SetupPage } from "./pages/SetupPage";

// Class/subject selection is removed for now — using static values until it's needed again.
const STATIC_CLASS: SchoolClass = { id: "class-6", name: "Class 6" };
const STATIC_SUBJECT: Subject = { id: "math", name: "Mathematics" };

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
  const [view, setView] = useState<View>(currentView);

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
      onOpenSetup={() => { window.location.hash = "setup"; }}
    />
  );
}

export default App;
