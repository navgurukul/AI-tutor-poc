import type { ClientTurnMetrics } from "../types";

/**
 * What one answer cost, and how good the retrieval behind it was.
 *
 * Collapsed by default and sitting under the citations, because it is for
 * whoever is tuning the tutor rather than for the student using it. Set
 * `VITE_SHOW_METRICS=false` to drop it from the build entirely.
 *
 * The panel leads with a stacked bar rather than a table on purpose. The
 * question being asked of these numbers is almost always "where did the time
 * go?", and on this stack the answer is nearly always prefill — the model
 * re-reading every retrieved passage on CPU before it emits a single token. A
 * column of figures makes that a subtraction; a bar makes it obvious, and makes
 * it obvious against the context-token count printed right beside it.
 */

const SHOW_METRICS = import.meta.env.VITE_SHOW_METRICS !== "false";

/** "820 ms" below a second, "4.2 s" above it — a turn spans both. */
function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(1)} s`;
}

function num(value: number | null | undefined, places = 3): string {
  return value === null || value === undefined ? "—" : value.toFixed(places);
}

interface Segment {
  key: string;
  label: string;
  value: number;
}

function Row({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="metrics__row">
      <span className="metrics__label">{label}</span>
      <span className="metrics__value">{value}</span>
      {hint && <span className="metrics__hint">{hint}</span>}
    </div>
  );
}

export function TurnMetricsPanel({ metrics }: { metrics: ClientTurnMetrics }) {
  if (!SHOW_METRICS) return null;

  const r = metrics.retrieval;

  // Ordered as the turn happens, so the bar reads left to right as the wait
  // did. Zero-length stages are dropped rather than rendered as slivers.
  const segments: Segment[] = [
    { key: "retrieval", label: "Retrieval", value: metrics.retrieval_ms },
    { key: "load", label: "Model load", value: metrics.load_ms },
    { key: "prefill", label: "Prefill", value: metrics.prefill_ms },
    { key: "decode", label: "Decode", value: metrics.decode_ms },
    { key: "retry", label: "Socratic retry", value: metrics.retry_ms },
    { key: "overhead", label: "Overhead", value: metrics.overhead_ms },
  ].filter((s) => s.value > 0);

  const measured = segments.reduce((sum, s) => sum + s.value, 0) || 1;

  return (
    <details className="metrics">
      <summary className="metrics__summary">
        <span className="citations__chevron" aria-hidden="true" />
        Timing &amp; retrieval · {ms(metrics.total_ms)}
      </summary>

      <div className="metrics__bar" role="img" aria-label="Where the time went">
        {segments.map((s) => (
          <span
            key={s.key}
            className={`metrics__seg metrics__seg--${s.key}`}
            style={{ width: `${(s.value / measured) * 100}%` }}
            title={`${s.label}: ${ms(s.value)}`}
          />
        ))}
      </div>
      <ul className="metrics__legend">
        {segments.map((s) => (
          <li key={s.key} className="metrics__legend-item">
            <span className={`metrics__swatch metrics__seg--${s.key}`} aria-hidden="true" />
            {s.label} {ms(s.value)}
          </li>
        ))}
      </ul>

      <div className="metrics__group">
        <h4 className="metrics__heading">Latency</h4>
        <Row
          label="To first token"
          value={ms(metrics.ttft_ms)}
          hint="what the wait actually feels like — the rest decodes while it is being spoken"
        />
        {metrics.client_ttft_ms !== undefined && (
          <Row
            label="…including speech"
            value={ms(metrics.client_ttft_ms)}
            hint="measured in the browser, so it carries the capture the server never sees"
          />
        )}
        <Row
          label="Prefill"
          value={ms(metrics.prefill_ms)}
          hint={`${metrics.prompt_tokens} prompt tokens read before the first one is written`}
        />
        <Row
          label="Decode"
          value={ms(metrics.decode_ms)}
          hint={`${metrics.completion_tokens} tokens at ${metrics.tokens_per_second} tok/s`}
        />
        <Row
          label="Retrieval"
          value={ms(metrics.retrieval_ms)}
          hint={`embed ${ms(r.embed_ms)} · vector ${ms(r.dense_ms)} · keyword ${ms(
            r.lexical_ms,
          )}`}
        />
        {metrics.retry_ms > 0 && (
          <Row
            label="Socratic retry"
            value={ms(metrics.retry_ms)}
            hint="the reply lectured, so it was re-asked — a second full generation"
          />
        )}
        {metrics.load_ms > 0 && (
          <Row
            label="Model load"
            value={ms(metrics.load_ms)}
            hint="the model was not resident; keep_alive should normally prevent this"
          />
        )}
      </div>

      <div className="metrics__group">
        <h4 className="metrics__heading">Retrieval</h4>
        {r.abstained ? (
          <>
            <Row label="Passages used" value="none — answered unaided" />
            <Row label="Why" value={r.abstain_reason || "—"} />
          </>
        ) : (
          <>
            <Row
              label="Passages used"
              value={`${r.returned} of ${r.fused}`}
              hint={
                r.dropped_over_budget > 0
                  ? `${r.dropped_over_budget} dropped whole to stay inside the token budget`
                  : undefined
              }
            />
            <Row
              label="Context"
              value={`${r.context_tokens} / ${r.context_budget} tokens`}
              hint="this is what prefill spent its time on"
            />
            <Row
              label="Closest hit"
              value={num(r.best_distance)}
              hint={`${r.query_language} ceiling ${num(r.ceiling, 2)} · ${num(
                r.headroom,
              )} to spare`}
            />
            <Row
              label="Lead over runner-up"
              value={num(r.separation)}
              hint="a flat gap means the ranking between the top two is near-arbitrary"
            />
            <Row
              label="Found by both legs"
              value={`${r.both_legs} of ${r.returned}`}
              hint="vector and keyword search agreeing — not recall, but its absence is a warning"
            />
            <Row
              label="Funnel"
              value={`${r.dense_hits} → ${r.gate_survivors} gated → ${r.fused} fused`}
              hint={
                r.lexical_query
                  ? `keyword leg: ${r.lexical_hits} hits, ${r.lexical_eligible} eligible`
                  : "no keyword query survived the builder"
              }
            />
            {/* Null is not zero. A cross-lingual answer — the case this whole
                branch exists for — shares no wording with its English source
                by construction, so it is declined rather than scored, and the
                note says so where a 0.00 would have read as "the model
                ignored the textbook". */}
            {metrics.groundedness !== null && metrics.groundedness !== undefined ? (
              <Row
                label="Groundedness"
                value={metrics.groundedness.toFixed(2)}
                hint="how much of the answer's wording traces back to the passages — a low score means the model ignored them, not that it was wrong"
              />
            ) : (
              <Row
                label="Groundedness"
                value="not measured"
                hint={metrics.groundedness_note || undefined}
              />
            )}
          </>
        )}
      </div>
    </details>
  );
}
