/**
 * Interrupting Piper playback.
 *
 * `usePiper` creates its `Audio` element inside `playQueue()` and never keeps a
 * reference to it, so the hook cannot stop a sentence that is already playing —
 * `resetTTS()` only empties the pending queues, which silences everything *after*
 * the current sentence.
 *
 * Pausing the element is not enough on its own either: `playQueue` awaits a
 * promise that resolves only from that element's `ended` / `error` events, so a
 * bare `pause()` leaves the promise pending forever, `processingRef` stuck true,
 * and every later `speak()` silently ignored for the rest of the session.
 *
 * So stopping a sentence means two things: pause it (immediate silence) and then
 * dispatch the `ended` event `playQueue` is waiting for, letting it drain the
 * now-empty queue and reset its own state the way it normally would.
 */

const playing = new Set<HTMLMediaElement>();
let installed = false;

/**
 * A chunk already inside `await synthesize(...)` when Stop is pressed still
 * pushes its blob and starts playing once synthesis finishes. Suppression closes
 * that race: nothing is audible until the next turn calls `allowSpeech()`.
 */
let suppressed = false;

function silence(element: HTMLMediaElement): void {
  try {
    element.pause();
  } catch {
    // Element may already be torn down — dispatching `ended` still matters.
  }
  // Exactly what usePiper's playQueue awaits; without it the queue never drains.
  element.dispatchEvent(new Event("ended"));
}

/**
 * Tracks media elements while they play. Called once, before any speaking starts.
 */
export function installSpeechInterceptor(): void {
  if (installed || typeof HTMLMediaElement === "undefined") return;
  installed = true;

  const nativePlay = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function trackedPlay(this: HTMLMediaElement) {
    playing.add(this);
    const forget = () => playing.delete(this);
    this.addEventListener("ended", forget, { once: true });
    this.addEventListener("error", forget, { once: true });

    const started = nativePlay.call(this);
    if (suppressed) {
      silence(this);
      // pause() during a pending play() rejects; usePiper already catches this,
      // but a direct caller might not.
      return started.catch(() => undefined);
    }
    return started;
  };
}

/** Silences current playback and blocks anything still being synthesized. */
export function stopSpeech(): void {
  suppressed = true;
  for (const element of [...playing]) silence(element);
  playing.clear();
}

/** Re-arms playback for a new turn. */
export function allowSpeech(): void {
  suppressed = false;
}
