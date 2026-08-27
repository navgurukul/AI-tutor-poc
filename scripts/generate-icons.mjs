// Rasterises apps/desktop/assets/*.svg into the platform icon files the
// desktop shortcuts point at: AI-Tutor.ico (Windows .lnk) and AI-Tutor.icns
// (the macOS .app bundle).
//
//   node scripts/generate-icons.mjs
//
// Both outputs are committed, so nobody creating a shortcut has to run this —
// it's only needed after editing the source SVGs. Rendering goes through the
// headless Chrome this project already requires rather than ImageMagick or
// librsvg, so there's no extra thing to install; each size is rendered from
// the vector at its own resolution instead of downscaling one big bitmap, so
// the 16px favicon-sized entries stay crisp.
//
// macOS only (the .icns step shells out to Apple's iconutil). The .ico is
// packed here in plain JS, so no Windows tooling is involved either way.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const assetsDir = path.join(repoRoot, "apps", "desktop", "assets");

const CHROME_CANDIDATES = [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  path.join(process.env.HOME ?? "", "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
];

// Windows shows .lnk icons at everything from 16px (details view) to 256px
// (extra-large icons), and picks the nearest entry present.
const ICO_SIZES = [16, 24, 32, 48, 64, 128, 256];

// The names iconutil expects inside a .iconset directory; the @2x entries are
// what Retina displays actually draw.
const ICONSET_FILES = [
  ["icon_16x16.png", 16],
  ["icon_16x16@2x.png", 32],
  ["icon_32x32.png", 32],
  ["icon_32x32@2x.png", 64],
  ["icon_128x128.png", 128],
  ["icon_128x128@2x.png", 256],
  ["icon_256x256.png", 256],
  ["icon_256x256@2x.png", 512],
  ["icon_512x512.png", 512],
  ["icon_512x512@2x.png", 1024],
];

function findChrome() {
  const found = (process.env.BROWSER ? [process.env.BROWSER] : []).concat(CHROME_CANDIDATES);
  return found.find((c) => c && existsSync(c)) ?? null;
}

/** Renders `svgPath` to a transparent PNG of exactly size x size pixels. */
function renderPng(chrome, svgPath, size, outPath, workDir) {
  // The SVG goes into a zero-margin page rather than being loaded directly:
  // Chrome gives a bare SVG document the default 8px body margin, which would
  // offset and clip the icon.
  // The source's own width/height have to be stripped, not just overridden:
  // duplicate attributes in HTML keep the *first* occurrence, so appending a
  // second width would leave the icon at 1024 and Chrome would screenshot the
  // top-left corner of it rather than scaling it down. viewBox is what makes
  // the drawing scale to whatever size is set here.
  const svg = readFileSync(svgPath, "utf8").replace(/<svg([^>]*)>/, (_, attrs) => {
    const scrubbed = attrs.replace(/\s(?:width|height)\s*=\s*"[^"]*"/g, "");
    return `<svg${scrubbed} width="${size}" height="${size}">`;
  });
  const htmlPath = path.join(workDir, `frame-${size}.html`);
  writeFileSync(
    htmlPath,
    `<!doctype html><meta charset="utf-8">` +
      `<style>html,body{margin:0;padding:0;background:transparent;overflow:hidden}</style>${svg}`
  );

  const result = spawnSync(
    chrome,
    [
      "--headless",
      "--disable-gpu",
      "--hide-scrollbars",
      "--force-device-scale-factor=1",
      "--default-background-color=00000000",
      `--window-size=${size},${size}`,
      `--screenshot=${outPath}`,
      `file://${htmlPath}`,
    ],
    { stdio: ["ignore", "ignore", "pipe"] }
  );
  if (!existsSync(outPath)) {
    throw new Error(
      `Chrome failed to render ${path.basename(svgPath)} at ${size}px:\n${result.stderr}`
    );
  }
}

/** Packs PNGs into a Vista-style .ico (PNG-compressed entries, Windows 7+). */
function packIco(pngs) {
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // 1 = icon (2 would be cursor)
  header.writeUInt16LE(pngs.length, 4);

  const entrySize = 16;
  let offset = header.length + entrySize * pngs.length;
  const entries = pngs.map(({ size, data }) => {
    const entry = Buffer.alloc(entrySize);
    // 256 is stored as 0 — the field is a single byte, so 256 doesn't fit.
    entry.writeUInt8(size >= 256 ? 0 : size, 0);
    entry.writeUInt8(size >= 256 ? 0 : size, 1);
    entry.writeUInt8(0, 2); // palette colour count (0 for truecolour)
    entry.writeUInt8(0, 3); // reserved
    entry.writeUInt16LE(1, 4); // colour planes
    entry.writeUInt16LE(32, 6); // bits per pixel
    entry.writeUInt32LE(data.length, 8);
    entry.writeUInt32LE(offset, 12);
    offset += data.length;
    return entry;
  });

  return Buffer.concat([header, ...entries, ...pngs.map((p) => p.data)]);
}

function main() {
  const chrome = findChrome();
  if (!chrome) {
    console.error(
      "Could not find Chrome/Edge/Chromium to render the icons with. " +
        "Install one, or set BROWSER to its full path."
    );
    process.exit(1);
  }

  const workDir = mkdtempSync(path.join(tmpdir(), "ai-tutor-icons-"));
  try {
    mkdirSync(assetsDir, { recursive: true });

    // --- Windows .ico, from the full-bleed tile ---
    const winSvg = path.join(assetsDir, "app-icon.svg");
    console.log("==> Rendering Windows icon sizes...");
    const pngs = ICO_SIZES.map((size) => {
      const out = path.join(workDir, `win-${size}.png`);
      renderPng(chrome, winSvg, size, out, workDir);
      process.stdout.write(`    ${size}x${size}\n`);
      return { size, data: readFileSync(out) };
    });
    const icoPath = path.join(assetsDir, "AI-Tutor.ico");
    writeFileSync(icoPath, packIco(pngs));
    console.log(`    -> ${path.relative(repoRoot, icoPath)}`);

    // --- macOS .icns, from the inset-tile variant ---
    if (process.platform !== "darwin") {
      console.log("\nSkipping AI-Tutor.icns: iconutil is macOS-only. The committed one is unchanged.");
      return;
    }
    const macSvg = path.join(assetsDir, "app-icon-macos.svg");
    const iconset = path.join(workDir, "AI-Tutor.iconset");
    mkdirSync(iconset, { recursive: true });
    console.log("\n==> Rendering macOS icon sizes...");
    for (const [name, size] of ICONSET_FILES) {
      renderPng(chrome, macSvg, size, path.join(iconset, name), workDir);
      process.stdout.write(`    ${name}\n`);
    }
    const icnsPath = path.join(assetsDir, "AI-Tutor.icns");
    const iconutil = spawnSync("iconutil", ["-c", "icns", iconset, "-o", icnsPath], {
      stdio: ["ignore", "inherit", "inherit"],
    });
    if (iconutil.status !== 0) {
      throw new Error("iconutil failed to build the .icns");
    }
    console.log(`    -> ${path.relative(repoRoot, icnsPath)}`);
  } finally {
    rmSync(workDir, { recursive: true, force: true });
  }

  console.log("\nIcons regenerated. Commit them so shortcut creation needs no tooling.");
}

main();
