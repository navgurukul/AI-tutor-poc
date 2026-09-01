<#
.SYNOPSIS
  One-shot setup for the AI Tutor POC: installs frontend, desktop, and backend
  dependencies, creates local .env files, and downloads the Piper voice model
  files.

.USAGE
  From the repo root:  powershell -File scripts\setup.ps1
  Safe to re-run - every step is skipped if already done, and any step that
  failed or was interrupted partway (e.g. a dropped download) is detected and
  retried rather than falsely treated as complete.

  Requires Python 3 on PATH for the backend virtualenv (the Microsoft Store's
  "python" shim doesn't count - install a real one, e.g.
  'winget install Python.Python.3.12').

  After this finishes, start everything with:
    powershell -File scripts\start.ps1
#>

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest's progress bar is very slow in Windows PowerShell

$repoRoot    = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot "apps\frontend"
$desktopDir  = Join-Path $repoRoot "apps\desktop"
$backendDir  = Join-Path $repoRoot "apps\backend"
$modelsDir   = Join-Path $frontendDir "public\models"

function Step($message) {
    Write-Host ""
    Write-Host "==> $message" -ForegroundColor Cyan
}

# True only if the file exists AND is at least $minBytes large - catches
# partial/corrupt downloads left behind by an interrupted run, which a plain
# Test-Path would wrongly treat as "already done".
function Test-ValidFile($filePath, $minBytes) {
    if (-not (Test-Path $filePath)) { return $false }
    return (Get-Item $filePath).Length -ge $minBytes
}

# Downloads to a temp file first, then moves it into place - so a failed or
# interrupted download never leaves a corrupt file sitting at $outFile for a
# later Test-Path to be fooled by.
function Get-FileSafely($uri, $outFile) {
    $tempFile = "$outFile.download"
    if (Test-Path $tempFile) { Remove-Item $tempFile -Force }
    try {
        Invoke-WebRequest -Uri $uri -OutFile $tempFile
        Move-Item $tempFile $outFile -Force
    } catch {
        if (Test-Path $tempFile) { Remove-Item $tempFile -Force }
        throw "Download failed: $uri`n$($_.Exception.Message)"
    }
}

# The Microsoft Store's "python"/"python3" shims answer to Get-Command but
# fail as soon as they're run (they only exist to open the Store), so a real
# install has to be confirmed by actually running --version, not just found.
function Find-Python {
    foreach ($cmd in @("python", "py")) {
        $exe = Get-Command $cmd -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        try {
            $verOutput = & $exe.Source --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $verOutput -match "Python 3") { return $exe.Source }
        } catch {}
    }
    return $null
}

# 1. Frontend dependencies. In theory npm's postinstall hooks handle the
#    Piper WASM assets and the onnxruntime-web copy automatically - but npm's
#    allow-scripts guard blocks react-sts-hooks' own postinstall on some
#    machines (seen in testing), so step 1b below runs it explicitly too.
Step "Installing frontend dependencies..."
Push-Location $frontendDir
try {
    npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed in apps/frontend" }
} finally {
    Pop-Location
}

# 1b. Piper WASM assets (worker script + phonemizer wasm/data). Not covered
#     by our own postinstall - only react-sts-hooks' setup script fetches
#     these, and it's the one most likely to get silently skipped.
#
#     Gate on piper_phonemize.data specifically, not piper_worker.js - the
#     small files (including piper_worker.js) get copied first and always
#     succeed quickly, while the ~18MB data file is what actually fails on a
#     slow/dropped connection. Gating on the wrong file would make a failed
#     run look "done" on the next pass and skip re-fetching for good.
$piperDataPath = Join-Path $frontendDir "public\piper-wasm\piper_phonemize.data"
if (-not (Test-ValidFile $piperDataPath (10MB))) {
    Step "Fetching Piper WASM assets (react-sts-hooks postinstall didn't run, or was incomplete)..."
    Push-Location $frontendDir
    try {
        npx react-sts-setup
        if ($LASTEXITCODE -ne 0) { throw "react-sts-setup failed in apps/frontend" }
    } finally {
        Pop-Location
    }
    if (-not (Test-ValidFile $piperDataPath (10MB))) {
        throw "Piper WASM assets still missing/incomplete after react-sts-setup ran. Check the output above."
    }
} else {
    Step "Piper WASM assets already present - skipping."
}

# 2. Desktop launcher (no real dependencies today, but keep this consistent
#    in case any get added later).
Step "Installing desktop launcher dependencies..."
Push-Location $desktopDir
try {
    npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed in apps/desktop" }
} finally {
    Pop-Location
}

# 3. Backend virtualenv + Python packages. Windows venvs put executables in
#    .venv\Scripts, not .venv\bin - that's a real (not cosmetic) difference
#    from apps/backend/run.sh, which is written for macOS/Linux and won't run
#    natively here, so this replicates its steps for Windows instead of
#    calling it.
$backendVenv   = Join-Path $backendDir ".venv"
$backendPython = Join-Path $backendVenv "Scripts\python.exe"

if (-not (Test-Path $backendPython)) {
    Step "Creating backend virtualenv..."
    $systemPython = Find-Python
    if (-not $systemPython) {
        throw "Python 3 not found. Install it (e.g. 'winget install Python.Python.3.12') and re-run this script."
    }
    & $systemPython -m venv $backendVenv
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtualenv at $backendVenv" }
} else {
    Step "Backend virtualenv already exists - skipping creation."
}

Step "Installing backend Python packages..."
& $backendPython -m pip install --quiet --upgrade pip
& $backendPython -m pip install --quiet -r (Join-Path $backendDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed in apps/backend" }

$backendEnvPath = Join-Path $backendDir ".env"
$backendEnvExamplePath = Join-Path $backendDir ".env.example"
if (-not (Test-Path $backendEnvPath)) {
    Step "Creating apps/backend/.env from template..."
    Copy-Item $backendEnvExamplePath $backendEnvPath
} else {
    Step "apps/backend/.env already exists - leaving it as-is."
}

# 4. .env - not committed to git, so create it from the template if missing.
#    Defaults to mock API mode so the app is usable with no backend running.
$envPath = Join-Path $frontendDir ".env"
$envExamplePath = Join-Path $frontendDir ".env.example"
if (-not (Test-Path $envPath)) {
    Step "Creating apps/frontend/.env (mock API on, no backend needed yet)..."
    Copy-Item $envExamplePath $envPath
    (Get-Content $envPath) -replace 'VITE_USE_MOCK_API=false', 'VITE_USE_MOCK_API=true' |
        Set-Content $envPath
    Write-Host "Edit apps\frontend\.env later to point VITE_API_BASE_URL at a real backend." -ForegroundColor DarkGray
} else {
    Step "apps/frontend/.env already exists - leaving it as-is."
}

# 5. Piper voice model files - not an npm dependency, so nothing else fetches
#    these. Downloaded once from the official rhasspy/piper-voices repo.
#    Size-checked the same way as step 1b, and downloaded via Get-FileSafely
#    so an interrupted download can't masquerade as a completed one.
if (-not (Test-Path $modelsDir)) {
    New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
}

$onnxPath = Join-Path $modelsDir "en_US-amy-medium.onnx"
$jsonPath = Join-Path $modelsDir "en_US-amy-medium.json"
$baseUrl  = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium"

if (-not (Test-ValidFile $onnxPath (10MB))) {
    Step "Downloading Piper voice model (~60MB, one-time)..."
    Get-FileSafely "$baseUrl/en_US-amy-medium.onnx" $onnxPath
} else {
    Step "Voice model (.onnx) already present - skipping download."
}

if (-not (Test-ValidFile $jsonPath 100)) {
    Step "Downloading Piper voice config..."
    Get-FileSafely "$baseUrl/en_US-amy-medium.onnx.json" $jsonPath
} else {
    Step "Voice model config already present - skipping download."
}

# 6. Offline speech-to-text model for the Indian languages: AI4Bharat's
#    IndicConformer (CTC, int8), run by the backend via sherpa-onnx (the wheel
#    is installed with the other Python packages in step 3 - prebuilt, no
#    compiler). One ~188MB multilingual model covers Hindi/Gujarati/Kannada/
#    Marathi. English speech input is handled on-device by the browser.
$indicDir    = Join-Path $backendDir "models\indicconformer"
$indicModel  = Join-Path $indicDir "model.int8.onnx"
$indicTokens = Join-Path $indicDir "tokens.txt"
$indicBase   = "https://huggingface.co/meetsync/indic-conformer-onnx-sherpa/resolve/main"

if (-not (Test-Path $indicDir)) {
    New-Item -ItemType Directory -Force -Path $indicDir | Out-Null
}

if (-not (Test-ValidFile $indicModel (100MB))) {
    Step "Downloading IndicConformer STT model (~188MB, one-time)..."
    Get-FileSafely "$indicBase/model.int8.onnx?download=true" $indicModel
} else {
    Step "IndicConformer STT model already present - skipping download."
}

if (-not (Test-ValidFile $indicTokens 10000)) {
    Step "Downloading IndicConformer STT tokens..."
    Get-FileSafely "$indicBase/tokens.txt?download=true" $indicTokens
} else {
    Step "IndicConformer STT tokens already present - skipping."
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next: powershell -File scripts\start.ps1" -ForegroundColor Green
Write-Host "  (starts the backend, then opens the AI Tutor in a borderless window)"
