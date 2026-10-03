import { useEffect, useRef, useState } from "react";
import type { GoldenQuestion, TurnDetail } from "../types";
import { askTutorStream, fetchGolden, fetchTurnDetail } from "../services/api";
import { TurnDetailView } from "../components/TurnDetailPanel";
import { secs } from "../utils/secs";

interface RowResult {
  status: "running" | "done" | "error";
  answer?: string;
  detail?: TurnDetail | null;
  sessionId?: string;
  /** Share of the question's points found in the answer / in the excerpts read. */
  answerFacts?: number;
  contextFacts?: number;
  error?: string;
}

/** Share of `points` with at least one accepted substring in `text`. */
function factsFound(points: string[][], text: string): number {
  if (points.length === 0) return 0;
  const low = text.toLowerCase();
  return points.filter((alts) => alts.some((a) => low.includes(a.toLowerCase()))).length / points.length;
}

const pct = (v?: number) => (v === undefined ? "–" : `${Math.round(v * 100)}%`);

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

/**
 * The golden question set (the same 20 AFE-Learning-App benchmarks with), asked
 * through the app's own chat stream, one at a time, with every turn's timings,
 * retrieved passages and prompt open to inspection.
 *
 * Asked with no profile, as AFE does: retrieval searches every grade rather
 * than the one the profile names. Follow-ups continue their parent's session.
 * The command-line runner (scripts/eval/golden_latency.py) does the same and
 * writes the files; this is the same run you can watch.
 */
export function GoldenPage({ onBack }: { onBack: () => void }) {
  const [questions, setQuestions] = useState<GoldenQuestion[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, RowResult>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const sessions = useRef<Record<string, string>>({});
  const stopRef = useRef(false);

  useEffect(() => {
    fetchGolden()
      .then(setQuestions)
      .catch((e: Error) =>
        setLoadError(`${e.message}. Is the backend up, and is TURN_DETAIL_LOG on?`),
      );
  }, []);

  const patch = (id: string, row: RowResult) =>
    setResults((prev) => ({ ...prev, [id]: row }));

  async function runOne(q: GoldenQuestion): Promise<void> {
    const parent = q.followUpOf;
    if (parent && !sessions.current[parent]) {
      patch(q.id, { status: "error", error: `Run ${parent} first — this continues its session.` });
      return;
    }
    patch(q.id, { status: "running" });
    let turnId: string | undefined;
    let answer = "";
    let sessionId = "";
    try {
      await askTutorStream(
        { message: q.question, sessionId: parent ? sessions.current[parent] : undefined },
        {
          onStart: (sid, tid) => {
            sessionId = sid;
            turnId = tid;
          },
          onDone: (r) => {
            answer = r.answer;
          },
        },
      );
      sessions.current[q.id] = sessionId;
      const detail = turnId ? await fetchTurnDetail(turnId) : null;
      const context = (detail?.retrieval.chunks ?? []).map((c) => c.excerpt ?? "").join(" ");
      patch(q.id, {
        status: "done",
        answer,
        detail,
        sessionId,
        answerFacts: factsFound(q.points, answer),
        contextFacts: factsFound(q.points, context),
      });
    } catch (e) {
      patch(q.id, { status: "error", error: (e as Error).message });
    }
  }

  async function runAll() {
    if (!questions) return;
    stopRef.current = false;
    setRunning(true);
    sessions.current = {};
    setResults({});
    for (const q of questions) {
      if (stopRef.current) break;
      await runOne(q);
    }
    setRunning(false);
  }

  function download() {
    const blob = new Blob([JSON.stringify({ questions, results }, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `golden-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const done = Object.values(results).filter((r) => r.status === "done");
  const med = (pick: (d: TurnDetail) => number) =>
    median(done.flatMap((r) => (r.detail ? [pick(r.detail)] : [])));
  const medTtft = med((d) => d.llm.ttft_ms);
  const medPrefill = med((d) => d.llm.prefill_ms);
  const medDecode = med((d) => d.llm.decode_ms);
  const medOut = med((d) => d.llm.completion_tokens);

  return (
    <div className="app-shell">
      <header className="app-bar">
        <div className="app-brand">
          <span className="app-logo" aria-hidden="true">AI</span>
          <div className="app-titles">
            <span className="app-name">Golden set</span>
            <span className="app-context">{questions ? `${questions.length} questions` : "loading"}</span>
          </div>
        </div>
        <div className="app-bar-actions">
          <button className="appbar__setup" type="button" onClick={onBack}>Back to tutor</button>
        </div>
      </header>

      <main className="screen golden">
        {loadError && <p className="td-note">{loadError}</p>}

        <div className="golden__bar">
          <button className="golden__btn" type="button" disabled={!questions || running} onClick={runAll}>
            {running ? "Running…" : "Run all"}
          </button>
          {running && (
            <button className="golden__btn golden__btn--ghost" type="button" onClick={() => { stopRef.current = true; }}>
              Stop after this one
            </button>
          )}
          <button className="golden__btn golden__btn--ghost" type="button" disabled={done.length === 0} onClick={download}>
            Download JSON
          </button>
          {done.length > 0 && (
            <span className="golden__summary">
              {done.length} done · median first token <b>{medTtft === null ? "–" : secs(medTtft)}</b> · prefill{" "}
              <b>{medPrefill === null ? "–" : secs(medPrefill)}</b> · decode{" "}
              <b>{medDecode === null ? "–" : secs(medDecode)}</b> · output tokens <b>{medOut ?? "–"}</b>
            </span>
          )}
        </div>

        <div className="golden__scroll">
          <table className="golden__table">
            <thead>
              <tr>
                <th>id</th><th>question</th><th>first token</th><th>prefill</th><th>decode</th>
                <th>prompt tok</th><th>output tok</th><th>chunks sent/got</th><th>answer facts</th><th>context facts</th><th />
              </tr>
            </thead>
            <tbody>
              {(questions ?? []).map((q) => {
                const r = results[q.id];
                const d = r?.detail;
                const sent = d ? d.retrieval.chunks.filter((c) => c.sent).length : null;
                return (
                  <FragmentRow
                    key={q.id}
                    q={q}
                    r={r}
                    cells={
                      <>
                        <td>{d ? secs(d.llm.ttft_ms) : "–"}</td>
                        <td>{d ? secs(d.llm.prefill_ms) : "–"}</td>
                        <td>{d ? secs(d.llm.decode_ms) : "–"}</td>
                        <td>{d?.llm.prompt_tokens ?? "–"}</td>
                        <td>{d?.llm.completion_tokens ?? "–"}</td>
                        <td>{d ? `${sent}/${d.retrieval.chunks.length}` : "–"}</td>
                        <td>{pct(r?.answerFacts)}</td>
                        <td>{pct(r?.contextFacts)}</td>
                      </>
                    }
                    expanded={open === q.id}
                    onToggle={() => setOpen(open === q.id ? null : q.id)}
                    onRun={() => void runOne(q)}
                    disabled={running}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}

function FragmentRow(props: {
  q: GoldenQuestion;
  r?: RowResult;
  cells: React.ReactNode;
  expanded: boolean;
  onToggle: () => void;
  onRun: () => void;
  disabled: boolean;
}) {
  const { q, r, cells, expanded, onToggle, onRun, disabled } = props;
  return (
    <>
      <tr className={r?.status === "error" ? "golden__row--error" : ""}>
        <td><b>{q.id}</b></td>
        <td className="golden__q" title={q.question}>
          {q.question}
          {r?.status === "running" && <em> · running…</em>}
          {r?.status === "error" && <em> · {r.error}</em>}
        </td>
        {cells}
        <td className="golden__actions">
          <button className="golden__btn golden__btn--small" type="button" disabled={disabled || r?.status === "running"} onClick={onRun}>Run</button>
          {r?.status === "done" && (
            <button className="golden__btn golden__btn--small golden__btn--ghost" type="button" onClick={onToggle}>
              {expanded ? "Hide" : "Detail"}
            </button>
          )}
        </td>
      </tr>
      {expanded && r?.status === "done" && (
        <tr>
          <td colSpan={11} className="golden__detail">
            <p className="td-note"><b>Expected:</b> {q.answerShouldMention}</p>
            <p className="golden__answer"><b>Answer:</b> {r.answer}</p>
            {r.detail ? <TurnDetailView detail={r.detail} /> : <p className="td-note">No turn record.</p>}
          </td>
        </tr>
      )}
    </>
  );
}
