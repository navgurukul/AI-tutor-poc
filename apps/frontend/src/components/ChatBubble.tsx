import type { ChatMessage, Citation } from "../types";
import { TurnMetricsPanel } from "./TurnMetricsPanel";

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
 *
 * The metrics panel sits below them, collapsed the same way and for a different
 * reader: the citations are for the student checking the answer, the metrics
 * are for whoever is tuning the tutor that produced it.
 */
/**
 * Below this, the answer shares almost no wording with the passage it was
 * given, so the passage did not shape it -- labelling it "From your textbook"
 * turns a page number into false proof. Deliberately low: groundedness is word
 * overlap, and a correct paraphrase of the right passage measured 0.075 on
 * 2026-09-11, while the answers that ignored theirs scored 0.00-0.02.
 */
const UNSUPPORTED_BELOW = 0.05;

export function ChatBubble({ role, text, sources, metrics }: ChatMessage) {
  // null means "not measurable" (e.g. a Hindi answer from an English page),
  // which is not evidence either way -- only a real low score changes the label.
  const unsupported =
    typeof metrics?.groundedness === "number" &&
    metrics.groundedness < UNSUPPORTED_BELOW;
  return (
    <div className={`chat-bubble chat-bubble--${role}`}>
      {text}
      {sources && sources.length > 0 && (
        <details className="citations">
          <summary className="citations__summary">
            <span className="citations__chevron" aria-hidden="true" />
            {unsupported
              ? `Not drawn from your textbook · closest page ${sources.length}`
              : `From your textbook · ${sources.length}`}
          </summary>
          <ol className="citations__list">
            {sources.map((source, index) => (
              <li className="citations__item" key={`${source.page_start}-${index}`}>
                <div className="citations__row">
                  <span className="citations__page">{pageLabel(source)}</span>
                  <span className="citations__where">
                    <span className="citations__title">{source.title}</span>
                    {source.heading && (
                      <span className="citations__heading">{source.heading}</span>
                    )}
                  </span>
                </div>
                {source.text && (
                  <p className="citations__excerpt">{source.text}</p>
                )}
              </li>
            ))}
          </ol>
        </details>
      )}
      {metrics && <TurnMetricsPanel metrics={metrics} />}
    </div>
  );
}
