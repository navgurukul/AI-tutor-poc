<#
.SYNOPSIS
  Custom actions for the AI Tutor MSI. Also runnable by hand for diagnosis.

.DESCRIPTION
  Two modes, both invoked by the MSI as deferred, non-impersonated (so they run
  elevated in a per-machine install):

    -Mode configure   permissions on the mutable tree, plus device.json
    -Mode gates       prove the vendored runtime actually works

  Kept in one script, installed alongside the app, so that when a device fails
  to install an engineer can run exactly what the installer ran:

    powershell -ExecutionPolicy Bypass -File setup-actions.ps1 -Mode gates `
        -InstallRoot "C:\Program Files\AITutor" -DataRoot "C:\ProgramData\AITutor"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet("configure","gates")][string]$Mode,
    [Parameter(Mandatory)][string]$InstallRoot,
    [Parameter(Mandatory)][string]$DataRoot,
    [string]$SiteId = "",
    [string]$HubUrl = ""
)

$ErrorActionPreference = "Stop"

# MSI passes properties by textual substitution, so a property left unset
# arrives as its own literal placeholder rather than as an empty string.
foreach ($n in "SiteId","HubUrl") {
    if ((Get-Variable $n -ValueOnly) -match '^\[.*\]$') { Set-Variable $n -Value "" }
}

$log = Join-Path $DataRoot "logs\install-actions.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Log($m) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  [$Mode] $m"
    Add-Content -Path $log -Value $line
    Write-Host $line
}

function Invoke-Configure {
    Log "Setting permissions on $DataRoot"

    # BUILTIN\Users by SID, not by name: the name is localised and this ships
    # to machines whose Windows may not be English.
    $users = "*S-1-5-32-545"

    # Break inheritance and restate it, rather than layering a grant on top of
    # %ProgramData%'s permissive defaults.
    & icacls $DataRoot /inheritance:d              2>&1 | Out-Null
    & icacls $DataRoot /remove:g "$users"          2>&1 | Out-Null
    & icacls $DataRoot /grant "${users}:(OI)(CI)RX" 2>&1 | Out-Null

    # Only these subtrees are writable, and none of them holds an executable
    # that Windows would run: app\ holds Python source the launcher hash-checks,
    # the rest is data.
    foreach ($d in @("app","content","state","logs","inbox")) {
        $p = Join-Path $DataRoot $d
        New-Item -ItemType Directory -Force -Path $p | Out-Null
        & icacls $p /grant "${users}:(OI)(CI)M" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "icacls failed on $p (exit $LASTEXITCODE)" }
    }

    # Verify rather than trust: a half-applied ACL would leave content the
    # updater cannot rewrite, which surfaces much later as "updates silently
    # stopped working on some machines".
    $acl = (& icacls (Join-Path $DataRoot "app")) -join " "
    if ($acl -notmatch "S-1-5-32-545|Users") { throw "ACLs did not apply to $DataRoot\app" }
    Log "permissions applied and verified"

    $cfgDir = Join-Path $InstallRoot "config"
    New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
    $devicePath = Join-Path $cfgDir "device.json"

    # A reinstall or upgrade must not silently discard the site's identity.
    if (Test-Path $devicePath) {
        $existing = Get-Content $devicePath -Raw | ConvertFrom-Json
        if (-not $SiteId) { $SiteId = [string]$existing.site_id }
        if (-not $HubUrl) { $HubUrl = [string]$existing.hub_url }
    }
    @{
        site_id       = $SiteId
        hub_url       = $HubUrl
        channel       = "stable"
        installed_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    } | ConvertTo-Json | Set-Content $devicePath -Encoding UTF8
    Log "device.json written (site_id='$SiteId', hub_url='$HubUrl')"
}

function Invoke-Gates {
    $py     = Join-Path $InstallRoot "runtime\python\python.exe"
    $ollama = Join-Path $InstallRoot "runtime\ollama\ollama.exe"
    $site   = Join-Path $InstallRoot "runtime\python\Lib\site-packages"

    if (-not (Test-Path $py))     { throw "vendored python.exe missing at $py" }
    if (-not (Test-Path $ollama)) { throw "vendored ollama.exe missing at $ollama" }

    $env:PYTHONPATH = $site
    $env:PYTHONUTF8 = "1"
    # With $ErrorActionPreference = "Stop", a native command writing to stderr
    # raises NativeCommandError before the $LASTEXITCODE check runs, turning a
    # legible gate failure into a PowerShell traceback. Judge by exit code.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $v = & $py -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>&1
        if ($LASTEXITCODE -ne 0) { throw "vendored python.exe will not run: $v" }
        Log "python $v"

        # THE gate. sqlite-vec is a loadable SQLite extension; a CPython built
        # without extension support cannot load it. Vector search would then be
        # dead on this device and the failure is quiet -- the library is merely
        # reported "unavailable" and the tutor degrades to model-only answers,
        # which looks like a bad model rather than a broken install.
        $probe = "import sqlite3, sqlite_vec; c = sqlite3.connect(':memory:'); c.enable_load_extension(True); sqlite_vec.load(c); print(c.execute('select vec_version()').fetchone()[0])"
        $vec = & $py -c $probe 2>&1
        if ($LASTEXITCODE -ne 0) { throw "sqlite-vec cannot load; vector search would be dead on this device.`n$vec" }
        Log "sqlite-vec $vec"

        # sherpa-onnx backs offline speech and only ships on the multilingual
        # build; the English build does all speech in the browser, so its
        # absence there is correct. Gate on what was actually installed.
        $mods = "fastapi", "uvicorn", "pypdf"
        if (Test-Path (Join-Path $site "sherpa_onnx")) { $mods += "sherpa_onnx" }
        $modList = $mods -join ", "
        $imports = & $py -c "import $modList; print('ok')" 2>&1
        if ($LASTEXITCODE -ne 0) { throw "backend dependencies failed to import ($modList).`n$imports" }
        Log "$modList import"

        # Catches a missing MSVC runtime, which is the usual reason the ggml
        # runners fail to load on a clean image.
        $ov = & $ollama --version 2>&1
        if ($LASTEXITCODE -ne 0) { throw "vendored ollama.exe will not run (missing VC++ runtime?).`n$ov" }
        Log "ollama runs: $ov"
    }
    finally {
        $ErrorActionPreference = $prevEAP
        Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
    }
    Log "all gates passed"
}

try {
    if ($Mode -eq "configure") { Invoke-Configure } else { Invoke-Gates }
    exit 0
}
catch {
    Log "FAILED: $($_.Exception.Message)"
    exit 1
}
