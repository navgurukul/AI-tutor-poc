import { useEffect, useState } from "react";
import type { ChatMessage } from "../types";
import { fetchModelInfo, type TutorModelInfo } from "../services/api";
import { secs } from "../utils/secs";

/**
 * The strip along the bottom of the tutor: which model is answering, how much
 * context it gets, and how long this conversation's replies have taken to start.
 *
 * The mean covers every reply on screen that finished streaming -- the same
 * per-turn TTFT each bubble shows, so the two can be checked against each
 * other. A stopped reply has no measurement and is left out.
 */
export function StatusBar({ messages }: { messages: ChatMessage[] }) {
  const [model, setModel] = useState<TutorModelInfo | null>(null);

  const ttfts = messages.flatMap((m) => (m.metrics ? [m.metrics.ttftMs] : []));

  // Fetched on mount; if the backend wasn't up yet, tried again after each
  // reply, since a reply proves it is.
  useEffect(() => {
    if (model) return;
    const controller = new AbortController();
    void fetchModelInfo(controller.signal).then((info) => {
      if (info) setModel(info);
    });
    return () => controller.abort();
  }, [model, ttfts.length]);

  const meanTtft = ttfts.length
    ? ttfts.reduce((sum, ms) => sum + ms, 0) / ttfts.length
    : null;

  return (
    <footer className="status-bar" aria-label="Tutor status">
      <span className="status-bar__item">
        Model <b>{model?.name ?? "–"}</b>
      </span>
      <span className="status-bar__item" title="Tokens of prompt + reply per request (NUM_CTX)">
        Context <b>{model?.numCtx ? `${model.numCtx.toLocaleString()} tokens` : "–"}</b>
      </span>
      <span
        className="status-bar__item"
        title={
          meanTtft === null
            ? "No replies yet"
            : `Mean of ${ttfts.length} ${ttfts.length === 1 ? "reply" : "replies"} - ` +
              `fastest ${secs(Math.min(...ttfts))}, slowest ${secs(Math.max(...ttfts))}`
        }
      >
        Mean TTFT <b>{meanTtft === null ? "–" : secs(meanTtft)}</b>
        {ttfts.length > 0 && ` over ${ttfts.length} ${ttfts.length === 1 ? "reply" : "replies"}`}
      </span>
    </footer>
  );
}
