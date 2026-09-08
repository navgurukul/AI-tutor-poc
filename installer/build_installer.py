#!/usr/bin/env python3
"""Build the AI Tutor MSI and the single-file installer .exe.

WINDOWS ONLY. The `wix` tool installs and runs on macOS and Linux, but MSI
creation is not portable: WiX authors the installer database through the
Windows Installer native API (msi.dll), which has no counterpart on other
platforms. Verified -- on macOS every Directory/@Name is rejected with WIX0389,
and removing the directory element reaches the real error:

    System.DllNotFoundException: Unable to load shared library 'msi.dll'

Use a Windows machine, or the windows-latest job in
.github/workflows/installer.yml, which needs no Windows hardware.

    dotnet tool install --global wix --version 5.*
    wix extension add -g WixToolset.Util.wixext/5.*
    wix extension add -g WixToolset.BootstrapperApplications.wixext/5.*

Then, after packaging/build_payload.py has produced the payload:

    python3 installer/build_installer.py --payload build/payload

Outputs into build/dist:

    AITutor-<ver>.msi + AITutor-<ver>*.cab   the IT-manageable unit (Intune/SCCM/GPO)
    AITutor-<ver>.exe                        SINGLE FILE, everything embedded

Why both: the .exe is what you hand someone to copy onto a laptop; the .msi is
what a management system deploys, because Intune and SCCM want a package they
can detect, supersede and uninstall. They are built from the same source, so
they cannot drift.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def die(msg: str) -> "None":
    print(f"\n\033[31merror:\033[0m {msg}", file=sys.stderr)
    raise SystemExit(1)


def require_windows() -> None:
    if os.name == "nt":
        return
    die(
        f"MSI packaging requires Windows; this is {sys.platform}.\n"
        "  WiX runs here but cannot author an MSI: the database is written through\n"
        "  the Windows Installer native API (msi.dll), which does not exist off\n"
        "  Windows. On macOS this surfaces first as a spurious WIX0389 about\n"
        "  Directory/@Name, then as DllNotFoundException for msi.dll.\n"
        "\n"
        "  Build it on Windows, or push and let CI do it:\n"
        "      .github/workflows/installer.yml  (windows-latest)\n"
        "\n"
        "  Everything before this step is portable: packaging/build_payload.py\n"
        "  assembles the full payload on macOS or Linux, and packaging/windows/\n"
        "  install.ps1 installs that payload directly with no MSI at all."
    )


def find_wix() -> str:
    wix = shutil.which("wix")
    if wix:
        return wix
    # dotnet global tools are not always on PATH in CI shells.
    candidate = Path.home() / ".dotnet" / "tools" / ("wix.exe" if os.name == "nt" else "wix")
    if candidate.exists():
        return str(candidate)
    die(
        "the WiX build tool was not found.\n"
        "  install .NET 6+ then:\n"
        "    dotnet tool install --global wix --version 5.*\n"
        "    wix extension add -g WixToolset.Util.wixext/5.*\n"
        "    wix extension add -g WixToolset.BootstrapperApplications.wixext/5.*"
    )


def msi_version(payload_version: str) -> str:
    """MSI versions are a.b.c with each field bounded, and only the first three
    fields participate in upgrade comparison. Anything richer (a git tag, a
    pre-release suffix) has to be reduced to that here rather than silently
    truncated by the toolchain."""
    parts = payload_version.split("+")[0].split("-")[0].split(".")
    nums = [int(p) for p in parts[:3] if p.isdigit()]
    while len(nums) < 3:
        nums.append(0)
    if nums[0] > 255 or nums[1] > 255 or nums[2] > 65535:
        die(f"version {payload_version} does not fit the MSI a.b.c limits (255.255.65535)")
    return ".".join(str(n) for n in nums)


def preflight(payload: Path) -> None:
    """Resolve every source path the .wxs files reference, before invoking WiX.

    A missing SourceFile or an empty <Files> glob is by far the most common way
    this build fails, and WiX reports it as a light/candle error against a line
    number rather than as "your payload is incomplete". Checking here turns a
    confusing toolchain error into a sentence.
    """
    import re

    problems: list[str] = []
    for wxs in (HERE / "AITutor.wxs", HERE / "Bundle.wxs"):
        text = wxs.read_text()

        for raw in re.findall(r'(?:SourceFile|IconSourceFile)="([^"]+)"', text):
            if "$(var.MsiPath)" in raw:
                continue                       # produced by this script
            rel = raw.replace("$(var.PayloadDir)\\", "").replace("\\", "/")
            if raw == rel:
                target = HERE / rel            # sits beside the .wxs
            else:
                target = payload / rel
            if not target.is_file():
                problems.append(f"{wxs.name}: SourceFile not found -> {target}")

        for raw in re.findall(r'<Files\s+Include="([^"]+)"', text):
            rel = raw.replace("$(var.PayloadDir)\\", "").replace("\\", "/")
            base = rel.split("/**")[0]
            root = payload / base
            if not root.is_dir():
                problems.append(f"{wxs.name}: <Files> root missing -> {root}")
            elif not any(f.is_file() for f in root.rglob("*")):
                problems.append(f"{wxs.name}: <Files> matched nothing under {root}")

    if problems:
        die("payload does not match the installer sources:\n  " + "\n  ".join(problems))
    print("    preflight: every source path resolves")


def run(cmd: list[str], label: str) -> None:
    print(f"\n\033[36m==> {label}\033[0m")
    print("    " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        die(f"{label} failed (exit {proc.returncode})")


def sign(path: Path, args: argparse.Namespace) -> None:
    """Authenticode. SmartScreen, Defender reputation and AppLocker publisher
    rules all key off this and nothing else -- without it, the elevated first
    install is an unknown-publisher warning on every one of thousands of
    machines, which is how a rollout gets stopped by a school's IT policy."""
    if not args.sign_command:
        print(f"    NOT SIGNED: {path.name}")
        return
    cmd = args.sign_command.replace("{file}", str(path))
    print(f"\n\033[36m==> Signing {path.name}\033[0m")
    if subprocess.run(cmd, shell=True).returncode != 0:
        die(f"signing failed for {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--payload", default="build/payload")
    ap.add_argument("--out", default="build/dist")
    ap.add_argument("--version", help="override pins.json payload_version")
    ap.add_argument("--msi-only", action="store_true")
    ap.add_argument("--sign-command",
                    help='shell command to Authenticode-sign, with {file} as the placeholder, e.g. '
                         '"signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /n \'AI Labs\' {file}"')
    args = ap.parse_args()

    require_windows()

    payload = Path(args.payload)
    if not payload.is_absolute():
        payload = ROOT / payload
    if not (payload / "manifest.json").is_file():
        die(f"no payload at {payload}. Run packaging/build_payload.py first.")

    manifest = json.loads((payload / "manifest.json").read_text())
    version = args.version or manifest.get("payload_version", "1.0.0")
    ver = msi_version(version)

    total_gb = manifest.get("total_bytes", 0) / 1024**3
    print(f"payload : {payload}")
    print(f"          {manifest.get('file_count')} files, {total_gb:.2f} GB")
    print(f"version : {version}  (MSI {ver})")

    if not (payload / "runtime" / "vc_redist.x64.exe").is_file():
        die("runtime/vc_redist.x64.exe missing from the payload.\n"
            "  The Ollama runners are MSVC-built and will not load without it.\n"
            "  Re-run build_payload.py with the ollama step enabled.")

    preflight(payload)

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    wix = find_wix()

    # --- MSI ---------------------------------------------------------------
    msi = out / f"AITutor-{version}.msi"
    run([wix, "build",
         "-arch", "x64",
         "-ext", "WixToolset.Util.wixext",
         "-d", f"ProductVersion={ver}",
         "-d", f"PayloadDir={payload}",
         "-o", str(msi),
         str(HERE / "AITutor.wxs")],
        f"Building {msi.name}")
    sign(msi, args)

    cabs = sorted(out.glob("*.cab"))
    print(f"\n    MSI database : {msi.stat().st_size / 1048576:.1f} MB")
    print(f"    external cabs: {len(cabs)} file(s), "
          f"{sum(c.stat().st_size for c in cabs) / 1024**3:.2f} GB")
    print("    (the database is what Windows caches under C:\\Windows\\Installer;")
    print("     keeping the cabs external is what stops that being a second copy)")

    if args.msi_only:
        print(f"\n\033[32mMSI built.\033[0m  {msi}")
        return 0

    # --- single-file bundle ------------------------------------------------
    exe = out / f"AITutor-{version}.exe"
    run([wix, "build",
         "-arch", "x64",
         "-ext", "WixToolset.BootstrapperApplications.wixext",
         "-d", f"ProductVersion={ver}",
         "-d", f"PayloadDir={payload}",
         "-d", f"MsiPath={msi}",
         "-o", str(exe),
         str(HERE / "Bundle.wxs")],
        f"Building {exe.name}")
    sign(exe, args)

    print(f"\n\033[32mBuilt.\033[0m")
    print(f"  single file : {exe}  ({exe.stat().st_size / 1024**3:.2f} GB)")
    print(f"  msi + cabs  : {msi}")
    print( "\n  Device, one file, silent:")
    print(f"      AITutor-{version}.exe /quiet SITEID=MH-PUNE-042")
    print( "  Device, via a management system:")
    print(f"      msiexec /i AITutor-{version}.msi SITEID=MH-PUNE-042 /qn /l*v install.log")
    print( "      (the .cab files must sit beside the .msi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
