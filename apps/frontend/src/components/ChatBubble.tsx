import type { ChatMessage } from "../types";

export function ChatBubble({ role, text }: ChatMessage) {
  return <div className={`chat-bubble chat-bubble--${role}`}>{text}</div>;
}
