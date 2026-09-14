import type { SchoolClass, Subject } from "../types";

/**
 * What the student picks in the lobby, and what the tutor persona is built from.
 *
 * These two lists are deliberately short. Every value here becomes part of the
 * system prompt, and the system prompt is the cached prefix: Ollama reuses it
 * only against the request that immediately preceded it, so each distinct
 * (language x class x subject) combination is its own prefix that has to be
 * primed from cold. That prime costs ~35s on the target hardware. A long menu
 * is therefore not a free menu -- it is a longer list of cold starts.
 *
 * A "General" entry is kept first in both, and it is not filler. Naming a class
 * and subject was removed from this app once before because a fixed
 * "Class 6 - Mathematics" persona pushed every question, including Hindi
 * grammar ones, into sixth-grade-maths framing. Selecting General leaves those
 * lines out of the prompt entirely and restores that behaviour, so the
 * narrowing is opt-in rather than the default.
 */

// An empty `name` is the signal to the backend to omit the line: see
// build_system_prompt, which only adds "Today's focus is ..." and "Pitch the
// explanation so a ... student can follow it" when the field is non-empty.
export const CLASSES: SchoolClass[] = [
  { id: "general", name: "" },
  { id: "class-6", name: "Class 6" },
  { id: "class-7", name: "Class 7" },
  { id: "class-8", name: "Class 8" },
];

export const SUBJECTS: Subject[] = [
  { id: "general", name: "" },
  { id: "hindi", name: "Hindi" },
  { id: "mathematics", name: "Mathematics" },
  { id: "science", name: "Science" },
  { id: "social-science", name: "Social Science" },
  { id: "english", name: "English" },
];

/** One (class, subject, medium) combination that has books behind it. */
export interface Coverage {
  grade: number;
  subject: string;
  language?: string;
  documents: number;
  chunks: number;
}

const GENERAL_CLASS: SchoolClass = { id: "general", name: "" };
const GENERAL_SUBJECT: Subject = { id: "general", name: "" };

/** "Class 6" -> "class-6", matching the ids the lobby stores. */
export function classIdForGrade(grade: number): string {
  return `class-${grade}`;
}

export function gradeForClassId(id: string): number | null {
  const m = /^class-(\d+)$/.exec(id);
  return m ? Number(m[1]) : null;
}

/**
 * What the library holds for one selection.
 *
 * The lobby needs this because it cannot learn it from the warm-up: the warm-up
 * skips retrieval on purpose (its message is the literal string "warm up", so
 * anything it retrieved would be noise), and reporting its zero passages made
 * the lobby claim "no textbook for this class" while eighteen books sat in the
 * library.
 *
 * `mediumMismatch` is the case worth surfacing separately — books exist for the
 * class and subject, but none of them are in the language the tutor is set to,
 * so the corpus filter will exclude every one of them and the tutor will answer
 * unaided without ever saying why.
 */
export function libraryFor(
  coverage: Coverage[] | undefined,
  classId: string,
  subjectId: string,
  language: string,
): { documents: number; chunks: number; mediumMismatch: boolean; media: string[] } {
  const grade = gradeForClassId(classId);
  const matching = (coverage ?? []).filter(
    (c) =>
      (grade === null || c.grade === grade) &&
      (subjectId === "general" || subjectIdFor(c.subject) === subjectId),
  );
  const inMedium = matching.filter(
    (c) => !c.language || c.language.toLowerCase() === language.toLowerCase(),
  );
  const usable = inMedium.length ? inMedium : [];
  return {
    documents: usable.reduce((n, c) => n + c.documents, 0),
    chunks: usable.reduce((n, c) => n + c.chunks, 0),
    mediumMismatch: matching.length > 0 && inMedium.length === 0,
    media: [...new Set(matching.map((c) => c.language).filter(Boolean) as string[])],
  };
}

export function subjectIdFor(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, "-");
}

/**
 * Classes the library actually holds books for, plus "Any / general".
 *
 * Built from live coverage rather than a hard-coded list. The two used to
 * disagree — the upload page offered classes 1-12 while the lobby offered 6-8,
 * so a Class 5 Science book could be ingested and then never selected. Deriving
 * both from the same source makes that impossible by construction.
 */
export function classesFromCoverage(coverage: Coverage[] | undefined): SchoolClass[] {
  const grades = [...new Set((coverage ?? []).map((c) => c.grade))].sort((a, b) => a - b);
  return [GENERAL_CLASS, ...grades.map((g) => ({ id: classIdForGrade(g), name: `Class ${g}` }))];
}

/**
 * Subjects the library holds for one class, plus "Any / general".
 *
 * Labelled with the medium, because that is the difference between a book the
 * tutor can use and one it will silently ignore: the corpus is filtered by
 * medium, so a Hindi session finds nothing in an English-medium book. Showing
 * "Science (English)" is what makes that visible before the student waits for a
 * prime rather than after.
 */
export function subjectsFromCoverage(
  coverage: Coverage[] | undefined,
  classId: string | null | undefined,
): Array<Subject & { medium?: string }> {
  const grade = gradeForClassId(classId ?? "");
  const rows = (coverage ?? []).filter((c) => grade === null || c.grade === grade);
  const seen = new Map<string, Subject & { medium?: string }>();
  for (const row of rows) {
    const id = subjectIdFor(row.subject);
    if (!seen.has(id)) {
      seen.set(id, { id, name: row.subject, medium: row.language || undefined });
    }
  }
  return [GENERAL_SUBJECT, ...seen.values()];
}

/**
 * Teaching medium — the language the textbook itself is written in.
 *
 * Deliberately the same list the tutor speaks, and in this app the lobby's
 * language choice serves as both: the student picks Hindi, gets Hindi answers,
 * and the Hindi-medium books are what get pinned. Split the two only if a
 * school ever wants English-medium books explained in Hindi.
 */
export const MEDIUMS = ["Hindi", "English", "Marathi"] as const;

/** Shown in the dropdown; the stored `name` stays empty for the general case. */
export const GENERAL_LABEL = "Any / general";

/** Resolve a stored class id without needing a list — the id carries the grade. */
export function classById(id: string | null | undefined): SchoolClass {
  const grade = gradeForClassId(id ?? "");
  return grade === null ? GENERAL_CLASS : { id: id!, name: `Class ${grade}` };
}

/**
 * Resolve a stored subject id against live coverage.
 *
 * The name has to come from the library rather than a constant, because it is
 * sent to the backend and matched against `documents.subject` — "Social
 * Science" and "social-science" are not the same row.
 */
export function subjectById(
  id: string | null | undefined,
  coverage?: Coverage[],
): Subject {
  if (!id || id === "general") return GENERAL_SUBJECT;
  const row = (coverage ?? []).find((c) => subjectIdFor(c.subject) === id);
  return { id, name: row ? row.subject : id };
}
