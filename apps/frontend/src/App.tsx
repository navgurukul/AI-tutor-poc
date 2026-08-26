import type { SchoolClass, Subject } from "./types";
import { TutorPage } from "./pages/TutorPage";

// Class/subject selection is removed for now — using static values until it's needed again.
const STATIC_CLASS: SchoolClass = { id: "class-6", name: "Class 6" };
const STATIC_SUBJECT: Subject = { id: "math", name: "Mathematics" };

function App() {
  return <TutorPage schoolClass={STATIC_CLASS} subject={STATIC_SUBJECT} />;
}

export default App;
