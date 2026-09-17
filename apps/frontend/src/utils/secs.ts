/** Seconds to one decimal below a minute, then m/s -- 0.9s, 14.1s, 1m 12s. */
export function secs(ms: number): string {
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60_000);
  return `${m}m ${Math.round((ms % 60_000) / 1000)}s`;
}
