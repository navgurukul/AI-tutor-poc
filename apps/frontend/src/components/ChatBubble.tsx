import type { ChatMessage, Citation } from "../types";

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
export function ChatBubble({ role, text, sources }: ChatMessage) {
  return (
    <div className={`chat-bubble chat-bubble--${role}`}>
      {text}
      {sources && sources.length > 0 && (
        <details className="citations">
          <summary className="citations__summary">
            <span className="citations__chevron" aria-hidden="true" />
            From your textbook · {sources.length}
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
