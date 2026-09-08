# Single-file installer (MSI + bundled .exe)

Turns the payload from `packaging/build_payload.py` into two artifacts built
from one source, so they cannot drift:

| Artifact | Size | For |
|---|---|---|
| `AITutor-<ver>.exe` | ~3.5 GB | **one file.** Copy to a laptop, double-click or run silently. |
| `AITutor-<ver>.msi` + `.cab` files | ~3 MB + ~3.5 GB | Intune / SCCM / Group Policy, which want a package they can detect, supersede and uninstall. |

## The 3.5 GB problem, and why the MSI stays small

Windows Installer keeps a copy of every installed package under
`C:\Windows\Installer` for repair and uninstall. **If the cabinets are embedded
in the MSI, that cached copy includes the whole payload** — so a 3.5 GB MSI
costs 7 GB on every device, permanently. Across thousands of laptops that is
the difference between fitting on the disk and not.

So `AITutor.wxs` sets `MediaTemplate/@EmbedCab="no"`. The MSI database stays a
few MB (that is all Windows caches) and the payload rides in external `.cab`
files that are read during install and not retained.

The Burn bundle then wraps the small MSI *and* its cabs into one `.exe`, which
is what makes "copy one file" true without reintroducing the caching cost.
`Cache="remove"` on the chained packages stops Burn keeping its own third copy.

## Build — Windows only

**This step cannot run on macOS or Linux.** The `wix` tool installs and runs
cross-platform, but MSI *creation* does not: WiX writes the installer database
through the Windows Installer native API (`msi.dll`), which has no counterpart
on other platforms. Verified on macOS with WiX 5.0.2 — every `Directory/@Name`
is rejected with a spurious `WIX0389 ... is not a relative path`, and removing
the directory element reaches the real error:

```
System.DllNotFoundException: Unable to load shared library 'msi.dll'
```

`build_installer.py` checks the platform first and says so, rather than letting
you chase the misleading WIX0389.

Everything *before* this step is portable: `packaging/build_payload.py`
assembles the full payload on macOS or Linux, and `packaging/windows/install.ps1`
installs that payload directly on a device with no MSI involved at all.

### Option A — CI, no Windows machine needed

`.github/workflows/installer.yml` builds both artifacts on `windows-latest`.
Run it from the Actions tab, or push a `v*` tag. Leave `full_payload` off for a
fast schema-only build while iterating on the WiX sources; turn it on (or push
a tag) for a real, installable artifact.

### Option B — a Windows machine

```powershell
dotnet tool install --global wix --version 5.*
wix extension add -g WixToolset.Util.wixext/5.*
wix extension add -g WixToolset.BootstrapperApplications.wixext/5.*

python packaging\build_payload.py --out build\payload
python installer\build_installer.py --payload build\payload
```

Outputs land in `build/dist`. Useful flags:

```
--msi-only            skip the bundle
--version 1.2.0       override pins.json
--sign-command "..."  Authenticode, with {file} as the placeholder
```

Before calling WiX the script resolves every `SourceFile` and `<Files>` glob the
`.wxs` files reference. A missing file is otherwise reported by WiX as an error
against a line number rather than as "your payload is incomplete".

### Signing

Not optional for a real rollout. SmartScreen, Defender reputation and
AppLocker publisher rules all key off Authenticode and nothing else; unsigned,
the elevated first install is an unknown-publisher warning on every machine,
which is how a rollout gets stopped by a school's IT policy.

```bash
python3 installer/build_installer.py --payload build/payload \
  --sign-command 'signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /n "AI Labs" {file}'
```

Azure Trusted Signing (~$10/mo, CI-friendly via OIDC, no hardware token to
physically hold for every release) is the sane choice for a small team.

## Deploy

**One file, per device:**

```powershell
AITutor-1.0.0.exe                                    # interactive
AITutor-1.0.0.exe /quiet SITEID=MH-PUNE-042          # silent
AITutor-1.0.0.exe /quiet SITEID=MH-PUNE-042 HUBURL=http://10.42.7.9:8477
```

**Via a management system** (the `.cab` files must sit beside the `.msi`):

```powershell
msiexec /i AITutor-1.0.0.msi SITEID=MH-PUNE-042 /qn /l*v install.log
msiexec /x AITutor-1.0.0.msi /qn
```

Detection rule for Intune/SCCM: registry
`HKLM\SOFTWARE\AILabs\AITutor\Version` equals the shipped version. The MSI also
writes `InstallRoot` and `DataRoot` there.

**Golden image:** install on the reference machine, leave `SITEID` empty, and
inject it per site afterwards. `device.json` is preserved across reinstalls and
upgrades, so re-imaging does not discard a site's identity.

## What the MSI does

- Installs the runtime to `C:\Program Files\AITutor` (Administrators=F,
  Users=RX) and the mutable half to `C:\ProgramData\AITutor`.
- Runs `setup-actions.ps1 -Mode configure`: breaks ACL inheritance on the data
  root and grants Users **Modify on `app`, `content`, `state`, `logs`, `inbox`
  only**. That is what lets later updates apply without elevation, given IT has
  admin at provisioning time and not afterwards.
- Runs `setup-actions.ps1 -Mode gates` and **fails the install** if the vendored
  runtime is broken — chiefly if `sqlite-vec` cannot load, since that failure is
  quiet: the library is merely reported "unavailable" and the tutor silently
  degrades to model-only answers, which looks like a bad model rather than a
  broken install. Better to fail loudly at install than ship a shortcut that
  launches a subtly broken tutor. `SKIPGATES=1` bypasses, for debugging only.
- Refuses to install on 32-bit Windows, on anything below Windows 8.1, or with
  under 12 GB free (the payload is ~3.6 GB and a future runtime update needs
  room to stage a second copy before swapping).
- Registers in Add/Remove Programs with a proper icon and uninstall.

`setup-actions.ps1` is installed to `bin\`, so when a device fails an engineer
can run exactly what the installer ran:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Program Files\AITutor\bin\setup-actions.ps1" `
    -Mode gates -InstallRoot "C:\Program Files\AITutor" -DataRoot "C:\ProgramData\AITutor"
```

It logs to `C:\ProgramData\AITutor\logs\install-actions.log`.

## Status

**Verified here (WiX 5.0.2 + .NET 8 on macOS):** WiX cannot emit an MSI on this
platform, but it *does* parse and validate the sources before reaching
`msi.dll`, and that caught two real defects which would have failed the Windows
build too:

- `WIX0006` — `Property/@Value` may not be an empty string. `SITEID`, `HUBURL`
  and `SKIPGATES` declared `Value=""`; an MSI property with no `Value` is simply
  undefined, which is what was wanted.
- `WIX0020` / `WIX0400` — `bal:Condition` takes its expression as a `Condition`
  **attribute** in WiX v4+, not as inner text.

After those fixes both files validate clean. Re-running with POSIX separators
(so WiX can resolve the tree on macOS) leaves **only `WIX0389`**, which a
minimal three-line package proves fires for *any* `Directory/@Name` here — it is
the platform bug, not our schema.

Also verified: the MSI version reduction and its field limits (255.255.65535);
the payload, `vc_redist` and source-path preflight guards all fire with useful
messages.

**NOT verified — needs Windows:**

- Neither artifact has been built, so nothing downstream of schema validation
  is proven: cab generation, `<Files>` harvesting across ~4,000 runtime files,
  the `WixQuietExec64` custom action wiring, and Burn's chaining of the MSI.
  Use the CI workflow with `full_payload` off for a fast loop on these.
- The custom actions, the `icacls` sequence and the install gates have never
  run.
- Whether `<Files>` harvesting of ~4,000 runtime files produces acceptable
  build times and cab sizes.

Build the MSI first with `--msi-only` against a **small** payload
(`build_payload.py --skip-llm --skip-speech`) to shake out the schema quickly.
A full 3.5 GB cab build is slow and a poor debugging loop.
