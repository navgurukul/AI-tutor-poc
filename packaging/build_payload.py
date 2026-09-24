#!/usr/bin/env python3
"""Assemble the offline Windows payload for the AI Tutor.

Runs on macOS, Linux or Windows -- it only *downloads* Windows artifacts, it
never executes them, so CI does not need a Windows runner to build. (Windows is
still required to *verify* the result; see packaging/README.md.)

The output is a directory tree that install.ps1 lays straight down onto a
device, plus a manifest.json carrying a SHA-256 for every file so the installer
can prove what it is installing.

    python3 packaging/build_payload.py --out build/payload

Every step is idempotent and independently skippable; downloads are cached in
build/.cache and resumed, because these are 470 MB artifacts on school links.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A textbook that survived ingestion is hundreds of chunks; this only has to be
# high enough to catch a truncated or half-ingested corpus and low enough never
# to reject a genuinely small book someone is testing with.
MIN_CORPUS_CHUNKS = 50
PINS = json.loads((Path(__file__).resolve().parent / "pins.json").read_text())

# Browser-side speech assets: a Piper voice (~61 MB), the Piper WASM runtime
# (~19 MB) and onnxruntime-web (~27 MB). Whether these are dead weight is
# BRANCH-DEPENDENT and must never be hardcoded:
#
#   - the multilingual branch removed Piper-in-browser, leaving 107 MB of the
#     108 MB dist/ unreferenced;
#   - this English branch calls usePiper() from useTutorSession.ts and warms
#     the voice cache from main.tsx, so the same files are load-bearing and
#     pruning them ships a build whose speech silently fails at runtime.
#
# So detect it: prune only what the source demonstrably does not reference.
SPEECH_ASSETS = [
    "models",                             # indian-accent-60.onnx
    "piper-wasm",
    "ort-wasm-simd-threaded.jsep.wasm",   # onnxruntime-web
    "ort-wasm-simd-threaded.jsep.mjs",
    "ort.min.js",
    "README-ort.md",
]

# Anything in src/ mentioning these means the assets are in use.
SPEECH_MARKERS = ("piper", "onnxruntime", "usepiper", "voice_model", "ort.min")


def frontend_uses_browser_speech(frontend: Path) -> bool:
    src = frontend / "src"
    for f in src.rglob("*"):
        if f.suffix.lower() not in (".ts", ".tsx", ".js", ".jsx"):
            continue
        try:
            text = f.read_text(errors="ignore").lower()
        except OSError:
            continue
        if any(m in text for m in SPEECH_MARKERS):
            return True
    return False


class Step:
    """Section logging that makes a 40-minute build readable in CI output."""

    def __init__(self, msg: str):
        self.msg = msg

    def __enter__(self):
        print(f"\n\033[36m==> {self.msg}\033[0m", flush=True)
        self.t = time.time()
        return self

    def __exit__(self, *exc):
        if exc[0] is None:
            print(f"    done in {time.time() - self.t:.1f}s", flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url: str, dest: Path, approx_mb: int | None = None, expect_sha: str | None = None) -> Path:
    """Download with resume. curl, not urllib: curl.exe is in-box on Windows 10+
    and present on macOS/Linux, and it does not depend on a Python CA bundle
    being configured -- which on a fresh python.org install it often is not."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        if expect_sha:
            if sha256(dest) != expect_sha:
                print(f"    cached {dest.name} FAILED digest, refetching")
                dest.unlink()
            else:
                print(f"    cached {dest.name} ({dest.stat().st_size / 1048576:.0f} MB, digest ok)")
                return dest
        else:
            # Without a pinned digest an interrupted download is indistinguishable
            # from a complete one, and the cache would hand it to every later
            # build. Warn rather than fail: the first build of a new pin has
            # nothing to check against, which is exactly when the digest gets
            # recorded.
            size_mb = dest.stat().st_size / 1048576
            hint = f" (~{approx_mb} MB expected)" if approx_mb else ""
            print(f"    cached {dest.name} ({size_mb:.0f} MB){hint} - NO DIGEST PINNED, "
                  f"trusting the cache; add sha256 to pins.json: {sha256(dest)}")
            return dest
    hint = f" (~{approx_mb} MB)" if approx_mb else ""
    print(f"    fetching {dest.name}{hint}")
    subprocess.run(
        ["curl", "-fL", "--retry", "3", "--retry-delay", "2", "-C", "-",
         "--progress-bar", url, "-o", str(dest)],
        check=True,
    )
    if expect_sha:
        got = sha256(dest)
        if got != expect_sha:
            dest.unlink(missing_ok=True)
            raise SystemExit(f"DIGEST MISMATCH for {url}\n  expected {expect_sha}\n  got      {got}")
    return dest


def find_uv() -> str:
    """uv, not pip. pip's --platform does NOT override sys_platform when
    evaluating environment markers, so a macOS/Linux build machine resolves
    `uvloop; sys_platform != "win32"` as required and then fails -- there is no
    uvloop Windows wheel. uv evaluates markers against --python-platform."""
    found = shutil.which("uv")
    if found:
        return found
    raise SystemExit(
        "uv is required to cross-resolve Windows wheels.\n"
        "  install: curl -LsSf https://astral.sh/uv/install.sh | sh   (or: pipx install uv)"
    )


# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------

def step_frontend(payload: Path, skip_build: bool) -> None:
    fe = ROOT / "apps" / "frontend"
    dist = fe / "dist"
    if not skip_build:
        npm = shutil.which("npm")
        if not npm:
            raise SystemExit("npm not found. Install Node on the BUILD machine (devices never need it).")
        subprocess.run([npm, "ci"], cwd=fe, check=True)
        # Same-origin: the backend serves these, so the API base must be a
        # relative path, and the mock must be off on a real device.
        env = {**os.environ, "VITE_API_BASE_URL": "", "VITE_USE_MOCK_API": "false",
               "VITE_SHOW_METRICS": "false"}
        subprocess.run([npm, "run", "build"], cwd=fe, check=True, env=env)
    if not (dist / "index.html").is_file():
        raise SystemExit(f"No frontend build at {dist}. Drop --skip-frontend-build.")

    web = payload / "app" / "web"
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(dist, web)

    before = sum(f.stat().st_size for f in web.rglob("*") if f.is_file())
    if frontend_uses_browser_speech(fe):
        print(f"    browser speech IS used here - keeping the Piper/ORT assets "
              f"({before / 1048576:.1f} MB)")
        return
    for name in SPEECH_ASSETS:
        target = web / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    after = sum(f.stat().st_size for f in web.rglob("*") if f.is_file())
    print(f"    browser speech unreferenced - pruned "
          f"{before / 1048576:.1f} MB -> {after / 1048576:.1f} MB")


def step_python(payload: Path) -> None:
    cache = ROOT / "build" / ".cache"
    pin = PINS["python"]
    tgz = fetch(pin["url"], cache / f"cpython-win64-{pin['version']}.tar.gz", pin["approx_mb"], pin["sha256"])

    pydir = payload / "runtime" / "python"
    if pydir.exists():
        shutil.rmtree(pydir)
    pydir.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz) as tf:
        tmp = payload / "runtime" / "_pytmp"
        tf.extractall(tmp, filter="data")
        # the archive roots everything under python/
        shutil.move(str(tmp / "python"), str(pydir))
        shutil.rmtree(tmp, ignore_errors=True)
    if not (pydir / "python.exe").is_file():
        raise SystemExit(f"python.exe missing under {pydir} -- archive layout changed?")

    uv = find_uv()
    site = pydir / "Lib" / "site-packages"
    reqs_path = ROOT / "apps" / "backend" / "requirements.txt"

    # Local path requirements (`-e ../../libs/textbook-ingest[pdf]`) need two
    # things the pinned wheel resolve cannot give them:
    #   * the path is relative to the requirements FILE, but uv resolves it
    #     against the CWD -- from the repo root `../../libs` lands outside the
    #     checkout entirely, and the build dies with "Distribution not found";
    #   * `-e` writes an editable .pth pointing at this build machine's source
    #     tree, which does not exist on a device.
    # So they are split out, resolved absolutely, and installed non-editable.
    pinned, local = [], []
    for line in reqs_path.read_text().splitlines():
        s = line.strip()
        if s.startswith("-e ") or s.startswith("--editable "):
            local.append(s.split(None, 1)[1])
        elif s.startswith((".", "..", "/")) and not s.startswith("#"):
            local.append(s)
        else:
            pinned.append(line)

    tmp_reqs = payload / "runtime" / "_requirements-pinned.txt"
    tmp_reqs.write_text("\n".join(pinned) + "\n")
    print("    resolving Windows cp312 wheels")
    subprocess.run(
        [uv, "pip", "install", "--target", str(site),
         "--python-platform", "windows", "--python-version", "3.12",
         "--only-binary=:all:", "-r", str(tmp_reqs)],
        check=True,
    )
    tmp_reqs.unlink()

    for spec in local:
        # Split a trailing extras marker off the path: "../x[pdf]" -> "../x", "[pdf]".
        base, _, extras = spec.partition("[")
        target = (reqs_path.parent / base.strip()).resolve()
        if not target.is_dir():
            raise SystemExit(f"local requirement not found: {spec} -> {target}")
        wanted = f"{target}{'[' + extras if extras else ''}"
        print(f"    building local package {target.name} (non-editable, --no-deps)")
        # --no-deps: these libraries declare no runtime dependencies of their
        # own, and anything their extras pull in is already pinned above. It
        # also keeps a source build from dragging in an unpinned sdist.
        subprocess.run(
            [uv, "pip", "install", "--target", str(site),
             "--python-platform", "windows", "--python-version", "3.12",
             "--no-deps", wanted],
            check=True,
        )
        mod = target.name.replace("-", "_")
        if not (site / mod).is_dir():
            raise SystemExit(f"{mod} did not land in site-packages -- ingest code would be missing.")
        if list(site.glob("__editable__*")) or list(site.glob("*.pth")):
            raise SystemExit(f"{mod} installed as editable -- it would point at this build machine.")
    # Sanity: the two native packages the whole product depends on.
    if not (site / "sqlite_vec" / "vec0.dll").is_file():
        raise SystemExit("sqlite_vec/vec0.dll missing -- vector search would be dead on every device.")
    # sherpa-onnx backs offline STT/TTS and is only a dependency on branches
    # that have them. The English build does all speech in the browser, so its
    # absence there is correct, not a broken resolve.
    reqs = (ROOT / "apps" / "backend" / "requirements.txt").read_text().lower()
    if "sherpa-onnx" in reqs or "sherpa_onnx" in reqs:
        if not list((site / "sherpa_onnx").rglob("*.dll")):
            raise SystemExit("sherpa_onnx is required but its DLLs are missing -- offline STT/TTS would be dead.")
    else:
        print("    sherpa-onnx not required by this branch (browser-side speech)")
    if (site / "uvloop").exists():
        raise SystemExit("uvloop present in a Windows target -- marker resolution went wrong.")
    print(f"    site-packages: {sum(f.stat().st_size for f in site.rglob('*') if f.is_file()) / 1048576:.0f} MB")


def step_ollama(payload: Path) -> None:
    cache = ROOT / "build" / ".cache"
    pin = PINS["ollama"]
    # The pinned version goes in the cache filename. Without it, bumping the pin
    # silently reuses the previously downloaded zip -- a new pin has no digest to
    # check against, so fetch() trusts whatever is cached -- and the payload ships
    # the OLD runtime. That happened on the v0.12.3 -> v0.32.15 bump, where the
    # stale binary cannot even load the model the build is for.
    zpath = fetch(pin["url"], cache / f"ollama-win-{pin['version']}.zip",
                  pin["approx_mb"], pin["sha256"])

    odir = payload / "runtime" / "ollama"
    if odir.exists():
        shutil.rmtree(odir)
    odir.mkdir(parents=True)

    # drop wins over keep: keep_prefixes takes the whole of lib/ollama/ and the
    # GPU runners are excluded by subdirectory. Prefix-only inclusion is what
    # broke the v0.32.15 build -- see the pin note.
    keep, drop = tuple(pin["keep_prefixes"]), tuple(pin.get("drop_prefixes") or ())
    kept, stripped = 0, 0
    with zipfile.ZipFile(zpath) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if drop and name.startswith(drop):
                stripped += info.file_size
            elif name.startswith(keep):
                out = odir / name
                out.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, out.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                kept += info.file_size
            elif name == pin["vc_redist"]:
                # Ollama's runners are MSVC-built; the redistributable has to
                # ride along or they fail to load on a clean Windows image.
                out = payload / "runtime" / "vc_redist.x64.exe"
                with zf.open(info) as src, out.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            else:
                stripped += info.file_size
    # Assert the ENGINE, not just the CLI. ollama.exe alone starts, serves /api/tags
    # and then fails the first generate with a 500 -- a failure that only shows up on a
    # device, after a 2.4 GB copy.
    required = ("ollama.exe", "lib/ollama/llama-server.exe", "lib/ollama/libllama.dll")
    missing = [r for r in required if not (odir / r).is_file()]
    if missing:
        raise SystemExit(
            "Ollama runtime incomplete -- release layout changed, check keep_prefixes:\n"
            + "".join(f"      missing {m}\n" for m in missing)
        )
    print(f"    kept {kept / 1048576:.0f} MB, stripped {stripped / 1048576:.0f} MB of GPU runners")


def step_speech(payload: Path) -> None:
    """Offline STT/TTS models. Absent from the English-only variant, where all
    speech is browser-side and pins.json carries no `speech` section."""
    if "speech" not in PINS:
        print("    no speech models in this variant (browser-side speech) - skipping")
        return
    cache = ROOT / "build" / ".cache"
    sp = PINS["speech"]
    ic, models = sp["indicconformer"], payload / "runtime" / "models"

    icdir = models / "indicconformer"
    icdir.mkdir(parents=True, exist_ok=True)
    fetch(ic["model_url"], icdir / "model.onnx", ic["approx_mb"], ic["sha256"])
    fetch(ic["tokens_url"], icdir / "tokens.txt", None, None)

    tts = sp["piper_tts"]
    tdir = models / "tts"
    tdir.mkdir(parents=True, exist_ok=True)
    if not (tdir / tts["voice"] / "tokens.txt").is_file():
        arc = fetch(tts["url"], cache / f"{tts['voice']}.tar.bz2", tts["approx_mb"], tts["sha256"])
        with tarfile.open(arc, "r:bz2") as tf:
            tf.extractall(tdir, filter="data")
    if not (tdir / tts["voice"] / "tokens.txt").is_file():
        raise SystemExit("Piper voice did not extract as expected.")


def step_llm(payload: Path) -> None:
    """Stage Ollama's blobs/manifests directly, so no device ever pulls."""
    ollama = shutil.which("ollama")
    if not ollama:
        raise SystemExit(
            "ollama not found on the BUILD machine. It is needed once, here, to stage\n"
            "  model blobs into the payload. Devices never run it to pull.\n"
            "  Re-run with --skip-llm to build everything else."
        )
    dest = payload / "runtime" / "models" / "ollama"
    dest.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "OLLAMA_MODELS": str(dest)}
    # A serve bound to a scratch port owns the staging dir for the pulls.
    env["OLLAMA_HOST"] = "127.0.0.1:11436"
    proc = subprocess.Popen([ollama, "serve"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            time.sleep(0.5)
            r = subprocess.run(["curl", "-sf", "--max-time", "2",
                                "http://127.0.0.1:11436/api/version"],
                               capture_output=True)
            if r.returncode == 0:
                break
        else:
            raise SystemExit("staging ollama did not come up on 11436")
        for model in PINS["llm"]["models"]:
            print(f"    pulling {model} into the payload")
            subprocess.run([ollama, "pull", model], env=env, check=True)
    finally:
        proc.terminate()
        proc.wait(timeout=30)
    if not (dest / "blobs").is_dir() or not (dest / "manifests").is_dir():
        raise SystemExit("blobs/ or manifests/ missing -- staging failed.")


def step_app_and_content(payload: Path) -> None:
    src = ROOT / "apps" / "backend" / "app"
    dst = payload / "app" / "backend" / "app"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".pytest_cache"))

    db = ROOT / "apps" / "backend" / "data" / "library.db"
    cdir = payload / "content"
    cdir.mkdir(parents=True, exist_ok=True)
    if db.is_file():
        check_corpus(db)
        copy_corpus(db, cdir / "library.db")
    else:
        print("    WARNING: no library.db -- the device will answer without the textbook corpus.")

    for name in ("install.ps1", "uninstall.ps1", "launch.ps1", "AITutor.cmd",
                 "benchmark.py", "benchmark.cmd"):
        f = Path(__file__).resolve().parent / "windows" / name
        if f.is_file():
            shutil.copy2(f, payload / name)
    ico = ROOT / "apps" / "desktop" / "assets" / "AI-Tutor.ico"
    if ico.is_file():
        shutil.copy2(ico, payload / "AI-Tutor.ico")


def copy_corpus(db: Path, target: Path) -> None:
    """Copy library.db through SQLite, never as a file.

    The store runs in WAL mode, so a freshly ingested corpus lives mostly in
    library.db-wal until something checkpoints it. `shutil.copy2` of the .db
    alone therefore ships whatever was last checkpointed -- and it fails
    silently, because the file it produces is a perfectly valid database that
    simply has most of the book missing.

    That is not hypothetical. The build of 2026-09-16 shipped a corpus of 16
    chunks out of 327 this way: 4.5 MB of the book was sitting in the -wal, the
    metadata check passed because the embedding model and dims were right, and
    the manifest hashed the truncated file without complaint. On a device it
    would have looked like a tutor that had read three pages of the textbook.

    The backup API reads through the WAL and writes one self-contained file, so
    the result needs no -wal or -shm beside it. The row counts are compared
    afterwards, because the point is the content and not the mechanism.
    """
    import sqlite3

    def counts(conn) -> tuple:
        return (conn.execute("select count(*) from chunks").fetchone()[0],
                conn.execute("select count(*) from documents").fetchone()[0])

    target.unlink(missing_ok=True)
    # -wal and -shm from an earlier file-copy build would otherwise be read
    # alongside the new file and put back the very rows this is replacing.
    for suffix in ("-wal", "-shm"):
        target.with_name(target.name + suffix).unlink(missing_ok=True)

    source = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    written = sqlite3.connect(str(target))
    try:
        source.backup(written)
        want = counts(source)
        got = counts(written)
    finally:
        written.close()
        source.close()

    if got != want:
        raise SystemExit(
            f"library.db did not copy completely: source has {want[0]} chunks in "
            f"{want[1]} document(s), the copy has {got[0]} in {got[1]}.")
    print(f"    content: library.db ({target.stat().st_size / 1048576:.1f} MB, "
          f"{want[0]} chunks from {want[1]} document(s))")


def _branch_expects() -> dict:
    """What this branch's backend requires of a corpus.

    Parsed from source rather than imported: the build may run under any Python,
    and importing the app would drag in pydantic and the rest of the backend's
    dependencies just to read three constants. Defaults are the right values to
    compare against because no .env ships to a device -- the launcher supplies
    the whole configuration as environment variables.
    """
    import ast

    want: dict[str, str] = {}

    cfg = ast.parse((ROOT / "apps" / "backend" / "app" / "config.py").read_text())
    for node in ast.walk(cfg):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in ("rag_embedding_model", "rag_embedding_dims") and node.value:
                try:
                    want[node.target.id] = str(ast.literal_eval(node.value))
                except ValueError:
                    pass

    store = ast.parse((ROOT / "apps" / "backend" / "app" / "services" / "rag" / "store.py").read_text())
    for node in ast.walk(store):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "SCHEMA_VERSION":
                    try:
                        want["schema_version"] = str(ast.literal_eval(node.value))
                    except ValueError:
                        pass
    return want


def check_corpus(db: Path) -> None:
    """Refuse a library.db this branch's backend cannot open.

    Vectors from two embedding models are not comparable and the store refuses
    to mix them, so a corpus built with the wrong model does not fail loudly at
    runtime -- it degrades the tutor to model-only answers with the library
    merely reported "unavailable". Shipping that to a fleet means every device
    silently loses retrieval, so catch it here where it is one line to read.
    """
    import sqlite3

    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        meta = dict(conn.execute("select key, value from meta").fetchall())
        chunks = conn.execute("select count(*) from chunks").fetchone()[0]
        documents = conn.execute("select count(*) from documents").fetchone()[0]
        conn.close()
    except sqlite3.Error as exc:
        raise SystemExit(f"library.db could not be read: {exc}")

    # Metadata alone is not enough, and that gap already shipped once: a corpus
    # truncated by the WAL copy (see copy_corpus) had the right embedding model,
    # the right dims and the right schema, and 16 chunks of a 327-chunk book.
    # Every check here passed it.
    if documents < 1 or chunks < MIN_CORPUS_CHUNKS:
        raise SystemExit(
            f"library.db holds {chunks} chunk(s) in {documents} document(s), which is "
            f"too little to be a textbook (expected at least {MIN_CORPUS_CHUNKS}).\n"
            "\n"
            "  A corpus this small usually means the copy was truncated, or that an\n"
            "  ingestion failed part way. Check apps/backend/data/library.db with:\n"
            "      sqlite3 apps/backend/data/library.db 'select count(*) from chunks'\n"
            "  and re-ingest the PDFs if the source is short too.")

    expects = _branch_expects()
    want = {
        "embedding_model": expects.get("rag_embedding_model"),
        "embedding_dims": expects.get("rag_embedding_dims"),
        "schema_version": expects.get("schema_version"),
    }
    missing = [k for k, v in want.items() if v is None]
    if missing:
        raise SystemExit(
            f"could not determine what this branch expects of a corpus ({', '.join(missing)}); "
            "check apps/backend/app/config.py and services/rag/store.py")

    bad = {k: (meta.get(k), v) for k, v in want.items() if meta.get(k) != v}
    if bad:
        lines = "\n".join(f"      {k}: corpus has {got!r}, this branch needs {exp!r}"
                           for k, (got, exp) in bad.items())
        raise SystemExit(
            f"library.db does not match this branch:\n{lines}\n"
            "\n"
            "  The store refuses to mix embedding models, so this corpus would leave\n"
            "  every device answering without the textbooks while reporting the\n"
            "  library as unavailable -- a silent loss of retrieval across the fleet.\n"
            "\n"
            "  Either re-ingest the PDFs against this branch's backend, or move\n"
            "  apps/backend/data/library.db aside to build a package with no corpus."
        )
    print(f"    corpus: {meta.get('embedding_model')} / {meta.get('embedding_dims')} dims, "
          f"schema {meta.get('schema_version')} - matches this branch")


# Files the host OS scatters through a tree and that must never reach a device.
# A .DS_Store appears the moment Finder looks in a folder, so this cannot be
# handled by being careful -- it has to be swept before the manifest is written.
JUNK_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", ".localized"}
JUNK_PREFIXES = ("._",)          # AppleDouble sidecars


def prune_junk(payload: Path) -> int:
    """Remove what must never be hashed into the manifest.

    Host-OS droppings (.DS_Store and friends), and SQLite sidecars. The sidecars
    matter more than they look: merely OPENING library.db, even read-only, even
    just to check what it contains, recreates library.db-shm and library.db-wal
    beside it. Do that after the manifest is written and the payload no longer
    matches its own manifest; do it before, and a -wal is hashed into the
    manifest and then has to exist on every device forever.

    Both happened during the 2026-09-16 rebuild, in that order.
    """
    removed = 0
    for f in list(payload.rglob("*")):
        if not f.is_file():
            continue
        junk = (f.name in JUNK_NAMES
                or f.name.startswith(JUNK_PREFIXES)
                or f.name.endswith(("-wal", "-shm", "-journal")))
        if junk:
            f.unlink(missing_ok=True)
            removed += 1
    if removed:
        print(f"    pruned {removed} junk file(s) (.DS_Store, SQLite sidecars)")
    return removed


def write_manifest(payload: Path) -> None:
    prune_junk(payload)
    files, total = [], 0
    for f in sorted(payload.rglob("*")):
        if not f.is_file() or f.name == "manifest.json":
            continue
        rel = f.relative_to(payload).as_posix()
        size = f.stat().st_size
        total += size
        files.append({"path": rel, "size": size, "sha256": sha256(f)})
    manifest = {
        "product": "in.example.aitutor",
        "payload_version": PINS["payload_version"],
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                  capture_output=True, text=True).stdout.strip() or None,
        "pins": {
            "python": PINS["python"]["version"],
            "ollama": PINS["ollama"]["version"],
            "llm_models": PINS["llm"]["models"],
        },
        "total_bytes": total,
        "file_count": len(files),
        "files": files,
    }
    (payload / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"    {len(files)} files, {total / 1048576:.0f} MB total")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="build/payload")
    ap.add_argument("--skip-frontend-build", action="store_true",
                    help="reuse apps/frontend/dist instead of running npm")
    ap.add_argument("--skip-llm", action="store_true",
                    help="skip the 2.8 GB Ollama blob staging (needs ollama locally)")
    ap.add_argument("--skip-speech", action="store_true",
                    help="skip the 534 MB STT/TTS models")
    ap.add_argument("--only", nargs="*", metavar="STEP",
                    help="run only these: frontend python ollama speech llm app manifest")
    args = ap.parse_args()

    payload = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    payload.mkdir(parents=True, exist_ok=True)
    print(f"payload -> {payload}")
    print(f"version -> {PINS['payload_version']}")
    print(f"models  -> {', '.join(PINS['llm']['models'])}"
          f"{'' if 'speech' in PINS else '   (no backend speech models: browser-side speech)'}")

    want = (lambda s: True) if not args.only else (lambda s: s in args.only)

    if want("frontend"):
        with Step("Frontend: build and prune"):
            step_frontend(payload, args.skip_frontend_build)
    if want("python"):
        with Step("Runtime: vendored CPython + Windows wheels"):
            step_python(payload)
    if want("ollama"):
        with Step("Runtime: vendored Ollama (GPU runners stripped)"):
            step_ollama(payload)
    if want("speech") and not args.skip_speech and "speech" in PINS:
        with Step("Runtime: offline STT + TTS models"):
            step_speech(payload)
    if want("llm") and not args.skip_llm:
        with Step("Runtime: staging LLM blobs"):
            step_llm(payload)
    if want("app"):
        with Step("App + content + installer scripts"):
            step_app_and_content(payload)
    if want("manifest"):
        with Step("Manifest"):
            write_manifest(payload)

    print("\n\033[32mPayload assembled.\033[0m")
    print(f"  Next: copy {payload} to a Windows machine and run, elevated:")
    print("        powershell -ExecutionPolicy Bypass -File .\\install.ps1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
