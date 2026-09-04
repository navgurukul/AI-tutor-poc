/**
 * Cache-first fetch for Piper voice files, so a 60-75 MB `.onnx` is downloaded
 * once per browser and read from the Cache API on every later visit.
 *
 * Inlined from react-sts-hooks' `getCachedOrFetch` when that dependency was
 * dropped. The cache name is deliberately unchanged — renaming it would orphan
 * the voices users have already downloaded and silently re-fetch them.
 */

const CACHE_NAME = "piper-models-cache-v1";

export async function getCachedOrFetch(
  url: string,
  onProgress?: (loaded: number, total: number) => void,
): Promise<Blob> {
  try {
    const cache = await caches.open(CACHE_NAME);

    const cached = await cache.match(url);
    if (cached) {
      console.log(`[Piper] Cache hit: ${url}`);
      return cached.blob();
    }

    console.log(`[Piper] Downloading: ${url}`);
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch ${url}: ${response.statusText}`);
    }

    const contentLength = response.headers.get("Content-Length");
    const total = contentLength ? parseInt(contentLength, 10) : 0;

    // Read the body through a pass-through stream to report progress; the
    // response is cloned first so the original stays unconsumed.
    let toRead = response.clone();
    if (onProgress && response.body) {
      const reader = response.body.getReader();
      const stream = new ReadableStream({
        async start(controller) {
          let loaded = 0;
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            loaded += value.byteLength;
            onProgress(loaded, total);
            controller.enqueue(value);
          }
          controller.close();
        },
      });
      toRead = new Response(stream, response);
    }

    const blob = await toRead.blob();
    await cache.put(url, new Response(blob));
    return blob;
  } catch (error) {
    console.error("[Piper] Voice cache error:", error);
    throw error;
  }
}
