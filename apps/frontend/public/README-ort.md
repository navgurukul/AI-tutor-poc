`ort.min.js`, `ort-wasm-simd-threaded.jsep.mjs`, and `.jsep.wasm` in this folder are
onnxruntime-web's runtime, copied from `node_modules/onnxruntime-web/dist` by
`scripts/copy-ort-assets.mjs` (runs automatically on `npm install` via `postinstall`).

Why they're here: the Piper worker inside `react-sts-hooks` loads onnxruntime-web
from `${window.location.origin}/ort.min.js` at runtime, but the package neither
bundles onnxruntime-web nor declares it as a dependency — an undocumented gap.
Without these files present, `usePiper`'s `isReady` never becomes `true` (the
worker's `importScripts`/dynamic import fails silently and only logs
`[Piper] Init failed: ...` to the console).

These are gitignored (large binaries) — if they're missing, run `npm install`
again or `node scripts/copy-ort-assets.mjs` directly.
