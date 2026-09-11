import type { ChatMessage, Citation, TurnMetrics } from "../types";

/** Seconds to one decimal below a minute, then m/s -- 0.9s, 14.1s, 1m 12s. */
function secs(ms: number): string {
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60_000);
  return `${m}m ${Math.round((ms % 60_000) / 1000)}s`;
}

/**
 * What the turn cost, on the same row as the citations.
 *
 * Time to the first word only. That is the number a student actually
 * experiences as waiting -- once text is on screen they are reading, and the
 * time the rest of the answer takes to arrive is spent, not waited. Showing
 * both invited the two to be read as one budget, and the total is the half
 * that cannot be optimised without making the answer shorter.
 *
 * The whole-reply figure is not lost, just demoted to the tooltip, where it
 * still explains a turn that felt slow after the first word appeared.
 */
function TurnCost({ metrics }: { metrics: TurnMetrics }) {
  const rate = metrics.totalMs > 0 ? (metrics.chars / metrics.totalMs) * 1000 : 0;
  return (
    <span
      className="turn-cost"
      title={
        `full reply ${secs(metrics.totalMs)} - ` +
        `${metrics.chars} characters at about ${rate.toFixed(0)} per second`
      }
    >
      <span className="turn-cost__item">
        Response (TTFT) <b>{secs(metrics.ttftMs)}</b>
      </span>
    </span>
  );
}

/** "p. 63" for a single page, "pp. 63-64" for a passage that spans a break. */
function pageLabel({ page_start, page_end }: Citation): string {
  return page_start === page_end
    ? `p. ${page_start}`
    : `pp. ${page_start}-${page_end}`;
}

/**
 * One turn of the conversation.
 *
 * Tutor replies grounded in the library carry the passages that were put into
 * the prompt. They are collapsed by default: a student reading the answer does
 * not want a citation list in the way, but a student who doubts the answer --
 * or a teacher checking it -- needs to see the page it came from. Their absence
 * is meaningful too, and says the reply came from the model alone.
 */
export function ChatBubble({ role, text, sources, metrics }: ChatMessage) {
  const hasSources = !!sources && sources.length > 0;
  return (
    <div className={`chat-bubble chat-bubble--${role}`}>
      {text}
      {/* No citations, but a measured turn still has a cost worth showing --
          an ungrounded reply is the fast case, and that contrast is the point. */}
      {!hasSources && metrics && (
        <div className="turn-cost-row">
          <TurnCost metrics={metrics} />
        </div>
      )}
      {hasSources && (
        <details className="citations">
          <summary className="citations__summary">
            <span className="citations__chevron" aria-hidden="true" />
            From your textbook · {sources.length}
            {metrics && <TurnCost metrics={metrics} />}
          </summary>
          <ol className="citations__list">
            {sources.map((source, index) => (
              <li className="citations__item" key={`${source.page_start}-${index}`}>
                <span className="citations__page">{pageLabel(source)}</span>
                <span className="citations__where">
                  <span className="citations__title">{source.title}</span>
                  {source.heading && (
                    <span className="citations__heading">{source.heading}</span>
                  )}
                </span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
