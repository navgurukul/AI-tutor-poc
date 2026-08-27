// Opens the AI Tutor frontend as a borderless "app window" using the system's
// installed Chrome or Edge (--app mode), instead of bundling a full Electron
// runtime — keeps things light for the ~4GB RAM target device.
//
// Usage:
//   node launch.mjs         Production mode: build (if needed) + serve dist/ + launch window
//   node launch.mjs --dev   Development mode: run the Vite dev server (HMR) + launch window
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.join(__dirname, "..", "frontend");

const isDev = process.argv.includes("--dev");
const port = isDev ? 5180 : 4173;
const url = `http://localhost:${port}`;

// Chromium-family only: the borderless window relies on --app, and the shared
// speech model relies on --profile-directory. Both are Chrome/Edge features.
const BROWSER_CANDIDATES_BY_PLATFORM = {
  win32: [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    path.join(process.env.LOCALAPPDATA ?? "", "Google\\Chrome\\Application\\chrome.exe"),
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  ],
  darwin: [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    path.join(process.env.HOME ?? "", "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
  ],
  linux: [
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/microsoft-edge",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
  ],
};

function findBrowser() {
  const candidates = BROWSER_CANDIDATES_BY_PLATFORM[process.platform] ?? [];
  return candidates.find((candidate) => candidate && existsSync(candidate)) ?? null;
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
  // BROWSER lets someone point at an install outside the standard locations.
  const browser = process.env.BROWSER || findBrowser();
  if (!browser) {
    console.error(
      `Could not find Chrome or Edge in the usual ${process.platform} locations. ` +
        "Install one of them, or set BROWSER to its full path and re-run."
    );
    process.exit(1);
  }

  let serverProcess = null;

  // A desktop shortcut gets double-clicked again while the stack is still up
  // (closing the borderless window doesn't stop the server behind it), and
  // --strictPort makes that second `npm run dev` exit immediately. Reuse the
  // running server instead and go straight to opening a window, so relaunching
  // is instant rather than broken.
  if (await isServerUp()) {
    console.log(`Server already running on ${url} — reusing it.`);
  } else if (isDev) {
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

  // A named profile under Chrome's *default* User Data root, not a separate
  // --user-data-dir. --user-data-dir points at an entirely independent User
  // Data root, which isolates not just cookies/permissions but also Chrome's
  // installation-level component downloads (the on-device speech recognition
  // model among them) - so offline STT worked in a regular browser tab
  // (using the real profile, which already had that model) but not in the
  // app window (a from-scratch data root that could never get it without
  // re-downloading it independently). --profile-directory instead creates an
  // isolated profile *inside* the default root, sharing those downloads.
  console.log(`Launching borderless window via ${browser}`);
  const chrome = spawn(
    browser,
    [
      `--app=${url}`,
      "--new-window",
      "--window-size=1280,800",
      `--profile-directory=AI Tutor POC`,
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
