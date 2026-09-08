# Windows installation package

Builds a **fully offline** installer for the AI Tutor. A provisioned laptop
needs no internet, no Python, no Node.js, no separate Ollama install and no
prerequisites of any kind — everything rides in the payload.

This replaces `scripts/setup.ps1` and `scripts/start.ps1`, which required four
hand-installed prerequisites and downloaded ~1.3 GB of model weights *per
device at install time*.

---

## Two machines, two jobs

| | Build machine (once per release) | Device (×1000s) |
|---|---|---|
| Needs internet | yes | **no** |
| Needs Node + npm | yes | no |
| Needs `uv` | yes | no |
| Needs Ollama | yes (to stage blobs) | no |
| OS | macOS, Linux or Windows (payload); **Windows only** for the MSI | Windows 10 20H2+ / 11 |

## 1. Build the payload

```bash
# once
curl -LsSf https://astral.sh/uv/install.sh | sh

python3 packaging/build_payload.py --out build/payload
```

Roughly 40 minutes and ~5 GB of downloads on a first run; re-runs reuse
`build/.cache`. Useful flags while iterating:

```bash
--skip-frontend-build   # reuse apps/frontend/dist instead of running npm
--skip-llm              # skip the 1.26 GB of Ollama model blobs
--skip-speech           # no-op here: this variant ships no backend speech models
--only python ollama    # run just these steps
```

**`uv` is required and pip will not substitute.** pip's `--platform win_amd64`
does not override `sys_platform` when evaluating environment markers, so a
macOS or Linux build machine resolves `uvloop; sys_platform != "win32"` as
required and then fails — there is no uvloop wheel for Windows. `uv` evaluates
markers against `--python-platform windows`. This is verified in the build
script, which fails loudly if `uvloop` ever appears in a Windows target.

## 2a. Wrap it into a single file (recommended)

`build/payload` is a directory of ~4,000 files. For distribution, turn it into
one signed artifact:

```bash
python3 installer/build_installer.py --payload build/payload
```

That produces `AITutor-<ver>.exe` (one file, everything embedded) and
`AITutor-<ver>.msi` + cabs for Intune/SCCM/GPO.

**That step needs Windows** — MSI creation goes through `msi.dll` and does not
work on macOS or Linux, so use `.github/workflows/installer.yml` if you have no
Windows machine. Payload assembly (step 1) and direct install (step 2b) are
both fully portable. See
[installer/README.md](../installer/README.md) — including why the MSI keeps its
cabinets external, which matters because an embedded-cab MSI would cost 7 GB
per device rather than 3.5.

## 2b. Or install the payload directly

Useful while iterating, and it needs no WiX toolchain. Copy `build/payload` to
the machine (USB, network share, or bake it into the golden image) and run
**elevated, once**:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -SiteId MH-PUNE-042
```

The installer verifies every file against `manifest.json` before touching the
machine, installs the MSVC runtime, lays down both roots, sets ACLs, **proves
the vendored runtime actually works**, then creates the shortcuts. If any gate
fails it stops without leaving a shortcut that would launch a broken app.

Then: the **AI Tutor** icon on the desktop, or `AITutor.cmd`.

To remove: `uninstall.ps1` (add `-Purge` to delete the corpus and logs too).

---

## What lands where, and why

```
C:\Program Files\AITutor\        IMMUTABLE   Administrators=F, Users=RX
├── runtime\python\              vendored CPython 3.12 + Windows wheels
├── runtime\ollama\              ollama.exe + CPU ggml runners only
├── runtime\models\              Ollama blobs (qwen2.5:1.5b, nomic-embed-text)
├── bin\                         launch.ps1, AITutor.cmd, uninstall.ps1, icon
└── config\device.json           site_id, hub_url, channel

C:\ProgramData\AITutor\          MUTABLE     inheritance broken, explicit ACEs
├── app\current\                 backend\app\** + web\**      Users=Modify
├── content\current\library.db   the textbook corpus          Users=Modify
├── state\                       session, ollama HOME         Users=Modify
├── logs\                        launcher, backend, ollama    Users=Modify
└── inbox\                       drop zone for future updates Users=Modify
```

**Why two roots.** Everything executable is in Program Files because AppLocker's
default rules allow execution there and block `%ProgramData%`, and school AV
heuristics flag binaries launching from ProgramData. Everything a future
unattended update must rewrite is in ProgramData with `Users=Modify` granted
once by this elevated install — which is what lets updates apply **without
admin**, given IT only has admin at provisioning time.

`%ProgramData%`'s inherited ACL already grants Users create-file and gives
CREATOR OWNER full control of anything they create. The installer breaks
inheritance and states the permissions explicitly rather than relying on that.

---

## Layer sizes (measured, not estimated)

| Layer | On disk | Packed | Changes |
|---|---|---|---|
| runtime (CPython + Ollama + weights) | ~1.3 GB | ~1.3 GB | ~yearly |
| **app** (backend source + built web) | **548 KB** | **156 KB** | weekly |
| **content** (`library.db`) | **13 MB** | **5.6 MB** | per curriculum |

That 156 KB is the number the whole design rests on: a routine update over a
poor link is seconds, not hours, because the 1.3 GB runtime never moves. See
`/Users/mayur/.claude/plans/this-app-needs-to-crispy-riddle.md` for the full
four-layer update architecture this package is the foundation of.

**Two size wins are already banked in the build:**

- **Ollama: 3322 MB → 63 MB.** Only `ollama.exe` and the CPU `ggml` runners
  ship; `cuda_v12`, `cuda_v13` and `hip` are stripped, being dead weight on
  integrated-graphics laptops.
- **Browser speech assets are KEPT here, and that is deliberate.** On this
  branch `main.tsx` warms the Piper voice cache and `useTutorSession.ts` calls
  `usePiper()`, so `public/models` (a 61 MB voice), `public/piper-wasm` (19 MB)
  and the onnxruntime-web WASM (27 MB) are load-bearing. The build *detects*
  this rather than assuming it: `frontend_uses_browser_speech()` scans `src/`
  and only prunes what the source demonstrably does not reference. The
  multilingual branch removed Piper-in-browser, so the same files are dead
  weight there and get pruned. Never hardcode that list — pruning them here
  ships a build whose speech silently fails at runtime.

---

## What the installer proves before it finishes

These run against the *vendored* interpreter on the actual device, because a
runtime that assembles cleanly can still be broken on arrival:

1. `python.exe` runs and reports 3.12.
2. **`sqlite-vec` loads.** The critical one: it is a loadable SQLite extension,
   and a CPython built without extension support cannot load it. Vector search
   would then be dead on every device, and the failure is quiet — the library
   is merely reported "unavailable" and the tutor silently degrades to
   model-only answers.
3. `fastapi`, `uvicorn`, `pypdf`, `sherpa_onnx` import.
4. The vendored `ollama.exe` runs (this catches a missing MSVC runtime).

Skip with `-SkipGates` only when debugging the installer itself.

---

## Hardening applied in this package

The POC bound `0.0.0.0` with `CORS_ORIGINS=*` and no authentication, which put
the 80 MB PDF upload and the document `DELETE` route in reach of every peer on
the school Wi-Fi. The packaged build:

- binds **127.0.0.1** (`BIND_HOST`), and warns loudly if configured otherwise;
- adds **no CORS middleware at all** — the backend serves the frontend, so
  every request is same-origin;
- rejects requests whose **`Host`** header is not loopback, which blocks DNS
  rebinding that a loopback bind alone does *not* stop;
- rejects **cross-site writes** via `Sec-Fetch-Site`. This matters specifically
  because `multipart/form-data` is a CORS-*simple* content type: a hostile page
  can submit a PDF to the upload route with no preflight, so CORS never gets a
  chance to block it;
- serves **no `/docs`, `/redoc` or `/openapi.json`**;
- runs Ollama on **127.0.0.1:11435**, not 11434, so a machine that once had the
  official Ollama installed does not collide — and with `OLLAMA_ORIGINS` empty,
  since nothing browser-side talks to it.

Configuration is injected **entirely as environment variables** by `launch.ps1`.
There is deliberately no `.env` on a device: pydantic-settings ranks real
environment variables above dotenv values, so this is the single source of
truth. That is what structurally prevents the template drift which had every
POC install silently running at `NUM_CTX=3072` while the code default said
6144 — a mismatch the config comments note causes Ollama to truncate from the
front and drop the system prompt on Devanagari multi-passage prompts.

---

## Status: what is verified and what is not

**Verified on the build machine (macOS):**

- Windows wheel cross-resolution — 7 `.pyd` + 7 `.dll`, zero `.so`, PE headers
  confirmed, `sqlite_vec/vec0.dll` present, `uvloop` correctly absent.
- **The vendored CPython supports SQLite extension loading.** Both
  `DLLs/sqlite3.dll` and `DLLs/_sqlite3.pyd` export
  `sqlite3_enable_load_extension`. This was the single biggest risk to the
  whole approach and it is settled.
- Ollama zip structure and the keep/strip split (3322 MB → 63 MB).
- The backend serving the built frontend, mount ordering (`/health` and
  `/api/*` still win over the SPA mount), cache headers, the Host-header
  rejection, the cross-site write rejection, and `/docs` being absent when
  packaged. The existing 104-test suite passes against all of it.
- Payload assembly, pruning and manifest generation.

**NOT verified — needs a Windows machine:**

- `install.ps1`, `launch.ps1` and `uninstall.ps1` have never been executed.
  There is no PowerShell on the build box they were written on. Treat the
  first run as a debugging session, not a deployment.
- The `icacls` ACL calls.
- Whether `ollama serve` tolerates a **read-only** `OLLAMA_MODELS` directory.
  `OLLAMA_NOPRUNE=1` should stop the prune write, but if it insists on writing,
  move `runtime\models\ollama` into `%ProgramData%` with `Users=Read`.
- Peak memory across the whole stack. gemma2:2b (~1.6 GB) and bge-m3 (~1.2 GB)
  are both pinned resident via `OLLAMA_KEEP_ALIVE=-1` — about 1.26 GB here,
  well under the multilingual build's 2.8 GB — plus Chrome. Comfortable at
  8 GB, but measure before committing to a hardware spec.

## Before a fleet rollout

**This variant carries no model licence obligations, which is a real advantage
over the multilingual build.** `qwen2.5:1.5b` and `nomic-embed-text` are both
Apache-2.0, and Ollama is MIT. There is no Gemma Terms of Use to pass on to
each school, no GPL-3.0 espeak-ng (that ships inside the Piper *backend* voice,
which this build does not have), and no unverified third-party re-export of the
IndicConformer weights.

The Piper voice that *is* here runs in the browser and comes from the
`react-sts-hooks` package's own assets — still check its licence, but it is a
much smaller surface than a 470 MB acoustic model from an unaffiliated account.

What remains:

1. **Textbook copyright.** `library.db` is built from third-party PDFs and the
   tutor quotes them back with page citations. Redistributing that as a
   retrievable index to thousands of devices needs written permission per
   publisher. Record it per document when you build the corpus.
2. **Authenticode signing.** Not optional. SmartScreen, Defender reputation and
   AppLocker publisher rules all key off it; unsigned, the elevated first
   install is an unknown-publisher warning on every machine.
3. **A CI-buildable corpus.** Ingestion is HTTP-only today, so `library.db` is
   made by hand through the Library UI and is neither reproducible nor
   reviewable. A CLI ingest script would make the content layer a build
   artefact — see the phased plan for where that sits.
