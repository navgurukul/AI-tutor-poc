// Opens the AI Tutor frontend as a borderless "app window" using the system's
// installed Chrome or Edge (--app mode), instead of bundling a full Electron
// runtime — keeps things light for the ~4GB RAM target device.
//
// Usage:
//   node launch.mjs         Production mode: build (if needed) + serve dist/ + launch window
//   node launch.mjs --dev   Development mode: run the Vite dev server (HMR) + launch window
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.join(__dirname, "..", "frontend");

const isDev = process.argv.includes("--dev");
const port = isDev ? 5180 : 4173;
const url = `http://localhost:${port}`;

const BROWSER_CANDIDATES = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  path.join(process.env.LOCALAPPDATA ?? "", "Google\\Chrome\\Application\\chrome.exe"),
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
];

function findBrowser() {
  return BROWSER_CANDIDATES.find((candidate) => candidate && existsSync(candidate)) ?? null;
}

async function isServerUp() {
  try {
    await fetch(url, { signal: AbortSignal.timeout(1000) });
    return true;
  } catch {
    return false;
  }
}

async function waitForServer(timeoutMs = 60000) {
  const start = Date.now();
  while (!(await isServerUp())) {
    if (Date.now() - start > timeoutMs) throw new Error(`Timed out waiting for ${url}`);
    await new Promise((r) => setTimeout(r, 400));
  }
}

async function main() {
  const browser = findBrowser();
  if (!browser) {
    console.error("Could not find Chrome or Edge installed. Install one of them and try again.");
    process.exit(1);
  }

  let serverProcess = null;

  if (isDev) {
    console.log(`Starting Vite dev server on ${url} ...`);
    serverProcess = spawn(
      "npm",
      ["run", "dev", "--", "--port", String(port), "--strictPort"],
      { cwd: frontendDir, stdio: "inherit", shell: true, windowsHide: true }
    );
  } else {
    if (!existsSync(path.join(frontendDir, "dist"))) {
      console.log("No production build found — building the frontend first...");
      const build = spawnSync("npm", ["run", "build"], {
        cwd: frontendDir,
        stdio: "inherit",
        shell: true,
        windowsHide: true,
      });
      if (build.status !== 0) {
        console.error("Build failed.");
        process.exit(1);
      }
    }
    console.log(`Serving the offline build on ${url} ...`);
    serverProcess = spawn(
      "npm",
      ["run", "preview", "--", "--port", String(port), "--strictPort"],
      { cwd: frontendDir, stdio: "inherit", shell: true, windowsHide: true }
    );
  }

  await waitForServer();

  const profileDir = mkdtempSync(path.join(tmpdir(), "ai-tutor-app-"));
  console.log(`Launching borderless window via ${browser}`);
  const chrome = spawn(
    browser,
    [
      `--app=${url}`,
      "--new-window",
      "--window-size=1280,800",
      `--user-data-dir=${profileDir}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-extensions",
    ],
    { stdio: "ignore", detached: true }
  );
  chrome.unref();

  console.log("AI Tutor launched. Close the window, or Ctrl+C here, to stop the server.");

  const shutdown = () => {
    serverProcess?.kill();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
