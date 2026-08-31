// react-sts-hooks' usePiper caches model/config downloads in this bucket keyed
// by URL. If a request for one of those URLs ever 404s during dev (e.g. before
// the model files exist), Vite's SPA fallback serves index.html with a 200, and
// that HTML response gets cached as if it were the real file — usePiper then
// reuses it forever, the worker fails to parse it, and the mic silently never
// becomes ready. This purges any such bad entry before usePiper gets to read it.
const CACHE_NAME = "piper-models-cache-v1";

async function isStaleEntry(cache: Cache, url: string): Promise<boolean> {
  const cached = await cache.match(url);
  if (!cached) return false;
  const contentType = cached.headers.get("content-type") ?? "";
  return contentType.includes("text/html");
}

export async function ensureFreshVoiceModelCache(urls: string[]): Promise<void> {
  if (!("caches" in window)) return;
  try {
    const cache = await caches.open(CACHE_NAME);
    for (const url of urls) {
      if (await isStaleEntry(cache, url)) {
        await cache.delete(url);
      }
    }
  } catch {
    // Best-effort — if this fails, usePiper's own fetch still runs normally.
  }
}
