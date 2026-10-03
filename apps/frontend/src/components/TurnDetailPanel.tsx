import { useState } from "react";
import type { TurnDetail } from "../types";
import { fetchTurnDetail } from "../services/api";
import { secs } from "../utils/secs";

/**
 * One turn, laid open: where the time went, which passages were retrieved and
 * which of them the model actually read, and the exact prompt that was sent.
 *
 * The three questions a slow or wrong answer needs answered, in that order:
 * was it retrieval, prefill (prompt length) or decode (answer length); was the
 * right page found; and was it in the prompt. For the developer or whoever is
 * grading the device, not for the student, so it sits behind a disclosure.
 */
export function TurnDetailView({ detail }: { detail: TurnDetail }) {
  const { retrieval, llm, prompt } = detail;
  const parts = [
    { label: "Retrieval", ms: retrieval.ms, cls: "td-bar__seg--retrieval" },
    { label: "Prefill", ms: llm.prefill_ms, cls: "td-bar__seg--prefill" },
    { label: "Decode", ms: llm.decode_ms, cls: "td-bar__seg--decode" },
  ];
  const sum = parts.reduce((t, p) => t + p.ms, 0) || 1;

  return (
    <div className="td">
      <div className="td-bar" aria-hidden="true">
        {parts.map((p) => (
          <span
            key={p.label}
            className={`td-bar__seg ${p.cls}`}
            style={{ width: `${(p.ms / sum) * 100}%` }}
          />
        ))}
      </div>
      <dl className="td-grid">
        <div><dt>Retrieval</dt><dd>{secs(retrieval.ms)}</dd></div>
        <div><dt>Prefill</dt><dd>{secs(llm.prefill_ms)}</dd></div>
        <div><dt>Decode</dt><dd>{secs(llm.decode_ms)}</dd></div>
        <div><dt>First token</dt><dd>{secs(llm.ttft_ms)}</dd></div>
        <div><dt>Total</dt><dd>{secs(llm.total_ms)}</dd></div>
        <div><dt>Model load</dt><dd>{llm.load_ms ? secs(llm.load_ms) : "warm"}</dd></div>
        <div><dt>Prompt tokens</dt><dd>{llm.prompt_tokens}</dd></div>
        <div><dt>Output tokens</dt><dd>{llm.completion_tokens}</dd></div>
        <div><dt>Tokens/s</dt><dd>{llm.tokens_per_second}</dd></div>
      </dl>

      <h4 className="td-h">
        Retrieved · {retrieval.chunks.length} ({retrieval.mode ?? "legacy"} retrieval, top-k{" "}
        {retrieval.top_k}, budget {retrieval.budget}, {retrieval.context_chars} chars sent)
      </h4>
      {detail.followup && (
        <p className="td-note">
          Follow-up: searched with “{retrieval.query}”
        </p>
      )}
      {retrieval.chunks.length === 0 && (
        <p className="td-note">Nothing retrieved — the model answered from its own weights.</p>
      )}
      <ol className="td-chunks">
        {retrieval.chunks.map((c) => (
          <li key={c.chunk_id} className={c.sent ? "" : "td-chunk--cut"}>
            <div className="td-chunk__head">
              <b>{c.title}</b>
              {c.heading && <span> · {c.heading}</span>}
              {c.page_start > 0 && (
                <span> · p. {c.page_start === c.page_end ? c.page_start : `${c.page_start}-${c.page_end}`}</span>
              )}
              <span className="td-chunk__dist" title="cosine distance, smaller is closer">
                {c.distance !== null && `dist ${c.distance.toFixed(3)}`}
                {c.score !== undefined && ` score ${c.score.toFixed(4)}`}
                {c.matched_via && c.matched_via.length > 0 && ` via ${c.matched_via.join("+")}`}
              </span>
              <span className={c.sent ? "td-tag td-tag--ok" : "td-tag td-tag--cut"}>
                {c.sent ? `sent ${c.chars_sent}/${c.chars_retrieved} chars` : "cut by budget"}
              </span>
            </div>
            {c.excerpt && <blockquote>{c.excerpt.replace(/\s+/g, " ").trim()}</blockquote>}
          </li>
        ))}
      </ol>

      <details className="td-prompt">
        <summary>
          Prompt sent · {prompt.model} · {prompt.prompt_chars} chars
        </summary>
        <pre className="td-options">{JSON.stringify(prompt.options)}</pre>
        {prompt.messages.map((m, i) => (
          <div key={i}>
            <div className="td-role">{m.role}</div>
            <pre className="td-pre">{m.content}</pre>
          </div>
        ))}
      </details>
    </div>
  );
}

/** Fetches the record the first time it is opened. */
export function TurnDetailPanel({ turnId }: { turnId: string }) {
  const [detail, setDetail] = useState<TurnDetail | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "missing">("idle");

  const onToggle = (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    if (!e.currentTarget.open || detail || state === "loading") return;
    setState("loading");
    void fetchTurnDetail(turnId).then((d) => {
      setDetail(d);
      setState(d ? "idle" : "missing");
    });
  };

  return (
    <details className="td-panel" onToggle={onToggle}>
      <summary className="td-panel__summary">Timing &amp; retrieval</summary>
      {state === "loading" && <p className="td-note">Loading…</p>}
      {state === "missing" && (
        <p className="td-note">
          No record for this turn. Turn detail logging is off (TURN_DETAIL_LOG) or the turn is
          older than the backend’s recent window.
        </p>
      )}
      {detail && <TurnDetailView detail={detail} />}
    </details>
  );
}
