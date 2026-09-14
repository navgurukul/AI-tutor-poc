import { useCallback, useEffect, useRef, useState } from "react";
import { LanguageSelect } from "../components/LanguageSelect";
import { warmupTutor } from "../services/api";
import { checkSpeechToText, checkTextToSpeech } from "../services/readiness";
import {
  GENERAL_LABEL,
  classesFromCoverage,
  libraryFor,
  subjectsFromCoverage,
  type Coverage,
} from "../config/curriculum";
import type { TutorLanguage } from "../config/languages";
import type { SchoolClass, Subject } from "../types";

interface StartPageProps {
  schoolClass: SchoolClass;
  subject: Subject;
  language: TutorLanguage;
  /** What the library holds — the Class and Subject options are built from it. */
  coverage: Coverage[];
  onLanguageChange: (code: string) => void;
  onClassChange: (id: string) => void;
  onSubjectChange: (id: string) => void;
  /**
   * Everything is loaded and the prompt prefix is cached — open the tutor,
   * handing it the session the warm-up primed so the first question continues
   * it rather than forking from it.
   */
  onStart: (primedSessionId: string) => void;
  onOpenLibrary: () => void;
}

type StepState = "waiting" | "running" | "done" | "failed";

interface Step {
  key: string;
  label: string;
  hint: string;
  state: StepState;
  detail?: string;
}

const INITIAL_STEPS: Step[] = [
  {
    key: "stt",
    label: "Speech recognition",
    hint: "Loads the offline recogniser for this language",
    state: "waiting",
  },
  {
    key: "tts",
    label: "Tutor voice",
    hint: "Loads the offline voice that reads answers aloud",
    state: "waiting",
  },
  {
    key: "llm",
    label: "Tutor and textbook",
    hint: "Reads the textbook once so questions don't have to wait for it",
    state: "waiting",
  },
];

/**
 * The lobby: choose a language, then wait once instead of on the first question.
 *
 * On this hardware the first turn of a session was 18.5s to first token while
 * every turn after it was 3.6-3.9s (measured 2026-09-09). None of that gap is
 * the model thinking harder. It is the recogniser loading, the voice loading,
 * and above all the LLM reading the persona and the pinned textbook -- roughly
 * 1300 prompt tokens -- for the first time. Ollama reuses that work only
 * against the request that immediately preceded it, so once it is done, every
 * later question extends it and is nearly free.
 *
 * So the work is unavoidable; the only question is who waits for it. Here, a
 * progress list during setup is expected. On the first question it reads as a
 * broken tutor.
 *
 * The warm-up MUST use the same profile the chat page will send. The persona
 * embeds language, class and subject, so a prefix primed for one combination is
 * worthless to another -- warm with the wrong profile and the student pays the
 * full cost again on their first question, having already waited here.
 */
export function StartPage({
  schoolClass,
  subject,
  language,
  coverage,
  onLanguageChange,
  onClassChange,
  onSubjectChange,
  onStart,
  onOpenLibrary,
}: StartPageProps) {
  const [steps, setSteps] = useState<Step[]>(INITIAL_STEPS);
  const [preparing, setPreparing] = useState(false);
  const [ready, setReady] = useState(false);
  // Held so "Start learning" can hand it to the tutor: the first question must
  // CONTINUE this session, not open a new one. See WarmupResult.sessionId.
  const [primedSessionId, setPrimedSessionId] = useState("");
  // Something already failed, so stop re-running on its own and let the student
  // retry deliberately. Without this a backend that is down turns into a loop of
  // ~40s attempts.
  const [autoStopped, setAutoStopped] = useState(false);
  const runIdRef = useRef(0);
  // Read through a ref inside prepare() rather than closed over as a
  // dependency. `coverage` is a fresh array on every library fetch, and a new
  // identity in prepare's deps would retrigger the auto-prime — a second ~40s
  // prime for a label that is only descriptive.
  const coverageRef = useRef(coverage);
  useEffect(() => {
    coverageRef.current = coverage;
  }, [coverage]);

  const setStep = useCallback(
    (key: string, state: StepState, detail?: string) => {
      setSteps((prev) =>
        prev.map((s) => (s.key === key ? { ...s, state, detail } : s)),
      );
    },
    [],
  );

  /**
   * Throw away everything prepared so far.
   *
   * Any of the three choices changes the persona, and the persona IS the
   * cached prefix -- so a prime done for the old combination is not partially
   * useful to the new one, it is worth nothing. Bumping the run id also makes
   * an in-flight prepare() drop its results instead of marking steps done for
   * a selection the student has already moved off.
   */
  const invalidate = useCallback(() => {
    runIdRef.current++;
    setSteps(INITIAL_STEPS);
    setReady(false);
    setPreparing(false);
    // The old session was primed with the old persona; continuing it would put
    // the wrong class or language in front of every answer.
    setPrimedSessionId("");
    // A new selection deserves a fresh attempt even if the last one failed.
    setAutoStopped(false);
  }, []);


  const prepare = useCallback(async () => {
    const runId = ++runIdRef.current;
    setPreparing(true);
    setReady(false);
    setSteps(INITIAL_STEPS.map((s) => ({ ...s, state: "waiting", detail: undefined })));

    const alive = () => runId === runIdRef.current;

    // Speech and voice first: they are seconds, and a missing model here is
    // worth telling the teacher about before the long step starts.
    setStep("stt", "running");
    const stt = await checkSpeechToText(language.name);
    if (!alive()) return;
    setStep("stt", stt.ready ? "done" : "failed", stt.detail);

    setStep("tts", "running");
    const tts = await checkTextToSpeech(language.name);
    if (!alive()) return;
    setStep("tts", tts.ready ? "done" : "failed", tts.detail);

    // The long one. A missing voice or recogniser costs a feature; a cold model
    // costs every question, so this runs even if the two above failed.
    setStep("llm", "running");
    const started = performance.now();
    const warm = await warmupTutor({
      subject: subject.name,
      level: schoolClass.name,
      language: language.name,
    });
    if (!alive()) return;
    const took = (performance.now() - started) / 1000;
    if (warm) {
      // Report what the LIBRARY holds, not what the warm-up retrieved. The
      // warm-up skips retrieval by design, so its passage count is always zero
      // once the corpus is too large to pin -- which had the lobby announcing
      // "no textbook for this class" with eighteen books ingested.
      const lib = libraryFor(coverageRef.current, schoolClass.id, subject.id, language.name);
      const book = lib.mediumMismatch
        ? `books exist but only in ${lib.media.join(", ")} — switch the language to use them`
        : lib.documents > 0
          ? `${lib.documents} textbooks · ${lib.chunks} passages available`
          : "no textbook for this selection — answers come from the tutor's own knowledge";
      setStep("llm", "done", `${book} · ${warm.promptTokens} tokens in ${took.toFixed(0)}s`);
      setPrimedSessionId(warm.sessionId);
      // Speech is optional -- a student can read the answers. A cold model is
      // not, so readiness is gated on this step alone.
      setReady(true);
    } else {
      setStep("llm", "failed", "Could not reach the tutor model.");
      setAutoStopped(true);
    }
    setPreparing(false);
  }, [
    language.name,
    schoolClass.id,
    schoolClass.name,
    subject.id,
    subject.name,
    setStep,
    setAutoStopped,
  ]);

  /**
   * Start priming as soon as the page settles, rather than on a button press.
   *
   * The prime is a fixed cost -- ~1359 prompt tokens at ~35ms each on a cold
   * cache, so roughly 40s. It cannot be made cheaper, only moved. Waiting for a
   * click spends the student's attention on a progress bar; starting on mount
   * spends it while they are reading the page and checking their class, and for
   * a returning student whose choices are already remembered it is usually
   * finished before they reach for the button.
   *
   * The delay debounces the dropdowns: flipping through four classes should not
   * launch four 40s primes, and each one would invalidate the last anyway.
   */
  useEffect(() => {
    if (autoStopped) return;
    const timer = setTimeout(() => void prepare(), 700);
    return () => clearTimeout(timer);
  }, [prepare, autoStopped]);

  const anyFailure = steps.some((s) => s.state === "failed");

  return (
    <div className="start-page">
      <div className="start-card">
        <h1 className="start-title">AI Tutor</h1>
        <p className="start-sub">
          Pick a language, then let the tutor load. It only has to do this once.
        </p>

        <div className="start-row">
          <span className="start-row-label">Language</span>
          <LanguageSelect
            code={language.code}
            onChange={(code) => {
              invalidate();
              onLanguageChange(code);
            }}
            disabled={preparing}
          />
        </div>

        <div className="start-row">
          <span className="start-row-label">Class</span>
          <select
            className="start-select"
            value={schoolClass.id}
            disabled={preparing}
            onChange={(e) => {
              invalidate();
              onClassChange(e.target.value);
            }}
          >
            {classesFromCoverage(coverage).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name || GENERAL_LABEL}
              </option>
            ))}
          </select>
        </div>

        <div className="start-row">
          <span className="start-row-label">Subject</span>
          <select
            className="start-select"
            value={subject.id}
            disabled={preparing}
            onChange={(e) => {
              invalidate();
              onSubjectChange(e.target.value);
            }}
          >
            {subjectsFromCoverage(coverage, schoolClass.id).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name
                  ? s.medium
                    ? `${s.name} (${s.medium})`
                    : s.name
                  : GENERAL_LABEL}
              </option>
            ))}
          </select>
        </div>

        <ol className="start-steps">
          {steps.map((s) => (
            <li key={s.key} className={`start-step start-step-${s.state}`}>
              <span className="start-step-mark" aria-hidden="true">
                {s.state === "done" ? "✓" : s.state === "failed" ? "!" : s.state === "running" ? "…" : "·"}
              </span>
              <span className="start-step-text">
                <span className="start-step-label">{s.label}</span>
                <span className="start-step-hint">{s.detail ?? s.hint}</span>
              </span>
            </li>
          ))}
        </ol>

        {anyFailure && !preparing && (
          <p className="start-warn">
            Something didn't load. You can still continue — answers will appear
            as text, and anything missing will load on first use instead.
          </p>
        )}

        <div className="start-actions">
          {ready ? (
            <button
              type="button"
              className="start-primary"
              onClick={() => onStart(primedSessionId)}
            >
              Start learning
            </button>
          ) : autoStopped ? (
            <button
              type="button"
              className="start-primary"
              onClick={() => {
                setAutoStopped(false);
                void prepare();
              }}
            >
              Try again
            </button>
          ) : (
            <button type="button" className="start-primary" disabled>
              Getting ready…
            </button>
          )}
          <button type="button" className="start-secondary" onClick={onOpenLibrary}>
            Manage textbooks
          </button>
        </div>

        {preparing && (
          <p className="start-note">
            Reading the textbook takes about half a minute on this machine. Doing
            it now is what makes the questions fast.
          </p>
        )}
      </div>
    </div>
  );
}
