<#
.SYNOPSIS
  Offline installer for the AI Tutor. Needs no internet and no prerequisites.

.DESCRIPTION
  Everything the app runs on -- CPython, Ollama, the LLM weights, the speech
  models -- is inside this payload. Nothing is downloaded and nothing is
  installed from the internet, because a device being provisioned may never
  have seen a network.

  Two install roots, deliberately:

    C:\Program Files\AITutor    everything executable. Administrators only.
    C:\ProgramData\AITutor      app code, content, logs, state. Users=Modify.

  Executables live in Program Files because AppLocker's default rules allow
  execution there and block %ProgramData%, and school AV flags binaries that
  launch from ProgramData. The mutable half sits in ProgramData so that a
  later unattended update can replace app code and content WITHOUT elevation --
  which is the whole point, given IT only has admin at first install.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\install.ps1 -SiteId MH-PUNE-042
#>
[CmdletBinding()]
param(
    [string]$SiteId       = "",
    [string]$HubUrl       = "",
    [string]$InstallRoot  = "$env:ProgramFiles\AITutor",
    [string]$DataRoot     = "$env:ProgramData\AITutor",
    [switch]$Force,
    [switch]$SkipVerify,
    [switch]$SkipGates
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"
# Resolved defensively: $PSScriptRoot is populated in a script body but not,
# for instance, when the script is dot-sourced.
$payload = if ($PSScriptRoot) { $PSScriptRoot } elseif ($PSCommandPath) { Split-Path -Parent $PSCommandPath } else { (Get-Location).Path }

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "    $m" -ForegroundColor Green }
function Warn($m) { Write-Host "    $m" -ForegroundColor Yellow }

# --- 0. elevation ---------------------------------------------------------
$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this elevated (Administrator). Only the FIRST install needs admin; updates do not."
}

Step "AI Tutor offline installer"
$manifestPath = Join-Path $payload "manifest.json"
if (-not (Test-Path $manifestPath)) { throw "manifest.json not found beside install.ps1 -- is this a complete payload?" }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
Write-Host "    payload $($manifest.payload_version)  built $($manifest.built_utc)"
Write-Host "    $($manifest.file_count) files, $([math]::Round($manifest.total_bytes/1GB,2)) GB"

# --- 1. verify the payload before touching the machine ---------------------
if (-not $SkipVerify) {
    Step "Verifying payload integrity"
    $bad = 0; $n = 0
    foreach ($f in $manifest.files) {
        $p = Join-Path $payload ($f.path -replace '/', '\')
        if (-not (Test-Path -LiteralPath $p)) { Write-Host "    MISSING $($f.path)" -ForegroundColor Red; $bad++; continue }
        # -Force, because Get-Item without it silently returns nothing for a
        # hidden or system file even though Test-Path found it -- and then
        # .Length throws instead of reporting. -LiteralPath so a name with [ ]
        # is not read as a wildcard.
        $item = Get-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
        if (-not $item) { Write-Host "    UNREADABLE $($f.path)" -ForegroundColor Red; $bad++; continue }
        if ($item.Length -ne $f.size) { Write-Host "    SIZE    $($f.path)" -ForegroundColor Red; $bad++; continue }
        $n++
        if ($n % 400 -eq 0) { Write-Host "    ...$n verified" }
    }
    # Hashing 3.5 GB costs a few minutes; do it for everything that executes.
    foreach ($f in $manifest.files | Where-Object { $_.path -match '\.(exe|dll|pyd|py)$' }) {
        $p = Join-Path $payload ($f.path -replace '/', '\')
        if ((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -ne $f.sha256.ToUpper()) {
            Write-Host "    DIGEST  $($f.path)" -ForegroundColor Red; $bad++
        }
    }
    if ($bad -gt 0) {
        # Two very different causes, and the fix differs: a damaged copy needs
        # re-copying, while a hand-patched file needs the manifest regenerated
        # (the build does that automatically; a manual edit does not).
        throw @"
$bad payload file(s) failed verification.

  If you edited a file in this payload by hand, the manifest no longer
  describes it. Regenerate it on the build machine:
      python3 packaging/build_payload.py --out build/payload --only manifest
  and copy manifest.json across with the file you changed.

  Otherwise the copy is damaged: re-copy the payload. Do not install this.
"@
    }
    Ok "payload intact"
}

# --- 2. stop anything running ---------------------------------------------
if (Test-Path $InstallRoot) {
    if (-not $Force) { throw "$InstallRoot already exists. Re-run with -Force to reinstall over it." }
    Step "Stopping any running AI Tutor"
    Get-Process -Name "ollama" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "$InstallRoot*" } | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like "$InstallRoot*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

# --- 3. MSVC runtime -------------------------------------------------------
# Ollama's ggml runners are MSVC-built and fail to load on a clean image
# without this. Shipped inside the Ollama zip; installed from the payload.
$vc = Join-Path $payload "runtime\vc_redist.x64.exe"
if (Test-Path $vc) {
    Step "Installing Microsoft VC++ runtime (required by the Ollama runners)"
    $p = Start-Process $vc -ArgumentList "/install","/quiet","/norestart" -Wait -PassThru
    # 1638 = a newer version is already present, which is success for us.
    if ($p.ExitCode -notin 0,1638,3010) { Warn "vc_redist returned $($p.ExitCode); continuing" } else { Ok "runtime present" }
}

# --- 4. immutable half -----------------------------------------------------
Step "Installing runtime to $InstallRoot"
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
foreach ($d in @("runtime","bin","config")) { New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot $d) | Out-Null }
Copy-Item (Join-Path $payload "runtime\*") (Join-Path $InstallRoot "runtime") -Recurse -Force
foreach ($f in @("launch.ps1","AITutor.cmd","uninstall.ps1","AI-Tutor.ico","manifest.json",
                 "benchmark.py","benchmark.cmd")) {
    $src = Join-Path $payload $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $InstallRoot "bin") -Force }
}
Ok "runtime installed"

# --- 5. mutable half -------------------------------------------------------
Step "Installing app and content to $DataRoot"
foreach ($d in @("app\current","content\current","state","logs","inbox")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot $d) | Out-Null
}
Copy-Item (Join-Path $payload "app\*")     (Join-Path $DataRoot "app\current")     -Recurse -Force
if (Test-Path (Join-Path $payload "content\library.db")) {
    Copy-Item (Join-Path $payload "content\library.db") (Join-Path $DataRoot "content\current") -Force
    Ok "textbook corpus installed"
} else {
    Warn "no library.db in payload -- the tutor will answer without the textbook corpus"
}

# --- 6. ACLs ---------------------------------------------------------------
# %ProgramData%'s inherited ACL already grants Users create-file and gives
# CREATOR OWNER full control of whatever they create, which is broader and
# less predictable than what we want. Break inheritance and state it exactly.
Step "Setting permissions"
$users = "*S-1-5-32-545"   # BUILTIN\Users, by SID: survives non-English Windows
& icacls $DataRoot /inheritance:d              | Out-Null
& icacls $DataRoot /remove:g "$users"          | Out-Null
& icacls $DataRoot /grant "${users}:(OI)(CI)RX" | Out-Null
foreach ($d in @("app","content","state","logs","inbox")) {
    & icacls (Join-Path $DataRoot $d) /grant "${users}:(OI)(CI)M" | Out-Null
}
# Program Files keeps its inherited Administrators=F / Users=RX, which is right.
$acl = (& icacls $DataRoot) -join " "
if ($acl -notmatch "S-1-5-32-545|Users") { throw "ACLs did not apply to $DataRoot -- refusing to leave a half-configured install." }
Ok "Program Files locked; app/content/state/logs/inbox writable by Users"

# --- 7. gates: prove it runs BEFORE we make a shortcut ---------------------
$py = Join-Path $InstallRoot "runtime\python\python.exe"
if (-not $SkipGates) {
    Step "Verifying the vendored runtime actually works"

    # With $ErrorActionPreference = "Stop", ANY native command that writes to
    # stderr raises NativeCommandError before the $LASTEXITCODE check below can
    # run -- so a probe that fails for an expected reason reports as a
    # PowerShell traceback instead of the diagnosis these gates exist to give.
    # Judge these by exit code alone, then restore the strict default.
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {

    $ver = & $py -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "vendored python.exe failed to run.`n$ver" }
    Ok "python $ver"

    # THE gate. sqlite-vec is a loadable SQLite extension; a CPython built
    # without extension support cannot load it, and all vector search dies
    # silently with the library merely reported 'unavailable'.
    $probe = "import sqlite3,sqlite_vec; c=sqlite3.connect(':memory:'); c.enable_load_extension(True); sqlite_vec.load(c); print(c.execute('select vec_version()').fetchone()[0])"
    $env:PYTHONPATH = Join-Path $InstallRoot "runtime\python\Lib\site-packages"
    $v = & $py -c $probe 2>&1
    if ($LASTEXITCODE -ne 0) { throw "sqlite-vec cannot load -- vector search would be dead on this device.`n$v" }
    Ok "sqlite-vec $v"

    # sherpa-onnx backs offline speech and only ships on the multilingual build;
    # the English build does all speech in the browser, so its absence there is
    # correct rather than a broken payload. Gate on what was actually installed.
    $imports = "fastapi", "uvicorn", "pypdf"
    if (Test-Path (Join-Path $InstallRoot "runtime\python\Lib\site-packages\sherpa_onnx")) {
        $imports += "sherpa_onnx"
    }
    $importList = $imports -join ", "
    $out = & $py -c "import $importList" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "backend dependencies failed to import ($importList).`n$out" }
    Ok "$importList import"

    $ollama = Join-Path $InstallRoot "runtime\ollama\ollama.exe"
    $ov = & $ollama --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "vendored ollama.exe failed to run (missing VC++ runtime?).`n$ov" }
    Ok "ollama runs"

    }
    finally {
        $ErrorActionPreference = $prevEAP
        Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
    }
}

# --- 8. device config ------------------------------------------------------
Step "Writing device configuration"
$devicePath = Join-Path $InstallRoot "config\device.json"
if ((Test-Path $devicePath) -and -not $Force) {
    Ok "device.json exists - keeping site settings"
} else {
    @{
        site_id       = $SiteId
        hub_url       = $HubUrl
        channel       = "stable"
        installed_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        payload_version = $manifest.payload_version
    } | ConvertTo-Json | Set-Content $devicePath -Encoding UTF8
    Ok "site_id='$SiteId'"
}

# --- 9. shortcuts ----------------------------------------------------------
Step "Creating shortcuts"
$cmd = Join-Path $InstallRoot "bin\AITutor.cmd"
$ico = Join-Path $InstallRoot "bin\AI-Tutor.ico"
$ws  = New-Object -ComObject WScript.Shell
foreach ($dir in @("$env:PUBLIC\Desktop", "$env:ProgramData\Microsoft\Windows\Start Menu\Programs")) {
    if (-not (Test-Path $dir)) { continue }
    $lnk = $ws.CreateShortcut((Join-Path $dir "AI Tutor.lnk"))
    $lnk.TargetPath       = $cmd
    $lnk.WorkingDirectory = Join-Path $InstallRoot "bin"
    $lnk.Description      = "AI Tutor - offline"
    $lnk.WindowStyle      = 7          # start minimised; the tutor opens its own window
    if (Test-Path $ico) { $lnk.IconLocation = $ico }
    $lnk.Save()
}
Ok "all-users Desktop and Start Menu"

Write-Host "`nAI Tutor installed." -ForegroundColor Green
Write-Host "  Runtime : $InstallRoot"
Write-Host "  Data    : $DataRoot"
Write-Host "  Launch  : the 'AI Tutor' icon, or $cmd"
Write-Host "  Remove  : powershell -ExecutionPolicy Bypass -File `"$InstallRoot\bin\uninstall.ps1`""
