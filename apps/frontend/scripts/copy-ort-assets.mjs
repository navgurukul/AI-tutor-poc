// The Piper worker inside react-sts-hooks loads onnxruntime-web from the app's
// origin root (`${window.location.origin}/ort.min.js`), but the package doesn't
// bundle or declare onnxruntime-web as a dependency. Without this, the worker's
// `importScripts`/dynamic import silently fails and the voice model never
// reports "ready" (see public/README-ort.md).
import { copyFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.join(root, "..", "node_modules", "onnxruntime-web", "dist");
const outDir = path.join(root, "..", "public");

const files = ["ort.min.js", "ort-wasm-simd-threaded.jsep.mjs", "ort-wasm-simd-threaded.jsep.wasm"];

if (!existsSync(srcDir)) {
  console.warn("[copy-ort-assets] onnxruntime-web not found in node_modules, skipping.");
  process.exit(0);
}

for (const file of files) {
  copyFileSync(path.join(srcDir, file), path.join(outDir, file));
  console.log(`[copy-ort-assets] copied ${file}`);
}
