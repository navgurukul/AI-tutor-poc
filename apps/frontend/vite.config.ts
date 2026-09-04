import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Cross-origin isolation, so `SharedArrayBuffer` exists and onnxruntime-web can
// run Piper synthesis multi-threaded instead of on one core. Without these the
// worker silently falls back to a single thread, which is ~125-165 ms per
// character on the medium voices.
//
// COEP `require-corp` only constrains no-cors subresource loads; the backend
// calls to http://localhost:8000 are CORS requests, so they still pass. Any
// cross-origin asset added later must send CORS or CORP headers.
//
// These are dev/preview-server headers. A production host has to send the same
// two headers or synthesis drops back to single-threaded.
const crossOriginIsolation = {
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Embedder-Policy': 'require-corp',
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { headers: crossOriginIsolation },
  preview: { headers: crossOriginIsolation },
})
