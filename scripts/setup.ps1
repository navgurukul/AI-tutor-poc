<#
.SYNOPSIS
  One-shot setup for the AI Tutor POC: installs frontend, desktop, and backend
  dependencies, creates local .env files, and downloads the speech model files
  (English + Hindi TTS voices, and the IndicConformer speech-to-text model).

.USAGE
  From the repo root:  powershell -File scripts\setup.ps1
  Safe to re-run - every step is skipped if already done, and any step that
  failed or was interrupted partway (e.g. a dropped download) is detected and
  retried rather than falsely treated as complete.

.PREREQUISITES
  - Python 3 on PATH for the backend virtualenv (the Microsoft Store's "python"
    shim doesn't count - install a real one, e.g.
    'winget install Python.Python.3.12').
  - Ollama installed and running for the tutor's answers:
      winget install Ollama.Ollama       # then it runs in the tray
      ollama pull <model>                # the model set in apps/backend/.env
                                         # (OLLAMA_MODEL, default gemma2:2b ~1.6 GB)
    The exact 'ollama pull ...' line is printed at the end of this script.
  - ~700 MB of one-time model downloads happen below (IndicConformer ~470 MB,
    Whisper EN ~145 MB, Piper voices ~130 MB). Resumable - just re-run if the
    connection drops.

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

# The LLM is chosen by OLLAMA_MODEL in apps/backend/.env (falls back to the
# template, then to gemma2:2b). All the "pull the model" hints derive from this,
# so pointing the app at qwen2.5:1.5b or a bigger model just works.
function Get-OllamaModel {
    foreach ($f in @((Join-Path $backendDir ".env"), (Join-Path $backendDir ".env.example"))) {
        if (Test-Path $f) {
            $m = Select-String -Path $f -Pattern '^\s*OLLAMA_MODEL\s*=\s*(\S+)' |
                 Select-Object -First 1
            if ($m) { return $m.Matches[0].Groups[1].Value }
        }
    }
    return "gemma2:2b"
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
#
# Uses curl.exe (bundled with Windows 10 1803+), NOT Invoke-WebRequest: IWR goes
# through WinINet, which hangs/times out on this network and can't resume. curl
# resumes a partial temp file (-C -) and retries transient failures, so a
# dropped connection just means re-running the script picks up where it left off
# instead of starting the multi-hundred-MB download over.
function Get-FileSafely($uri, $outFile) {
    $tempFile = "$outFile.download"
    $curl = "$env:SystemRoot\System32\curl.exe"
    if (-not (Test-Path $curl)) { $curl = "curl.exe" }
    & $curl --fail --location --retry 5 --retry-delay 3 `
            --continue-at - --output $tempFile $uri
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed ($LASTEXITCODE): $uri`nRe-run scripts\setup.ps1 to resume."
    }
    Move-Item $tempFile $outFile -Force
}

# Finds a real Python 3. The Microsoft Store's "python"/"python3" shims answer
# to Get-Command but only open the Store when run, so every candidate is
# confirmed by actually running --version. Also probes the standard python.org
# install folders, since that installer often isn't added to PATH.
function Find-Python {
    $candidates = @()
    foreach ($cmd in @("python", "python3", "py")) {
        $exe = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($exe) { $candidates += $exe.Source }
    }
    foreach ($glob in @(
            "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
            "$env:ProgramFiles\Python3*\python.exe",
            "${env:ProgramFiles(x86)}\Python3*\python.exe",
            "$env:USERPROFILE\AppData\Local\Programs\Python\Python3*\python.exe")) {
        $candidates += (Get-ChildItem $glob -ErrorAction SilentlyContinue |
                        Sort-Object FullName -Descending |
                        ForEach-Object { $_.FullName })
    }
    foreach ($path in ($candidates | Select-Object -Unique)) {
        # Skip the WindowsApps shims outright - they hang/relaunch when run here.
        if ($path -like "*\WindowsApps\*") { continue }
        try {
            $verOutput = & $path --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $verOutput -match "Python 3") { return $path }
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
        throw @"
No real Python 3 found. Checked PATH plus the usual install folders
(%LOCALAPPDATA%\Programs\Python, %ProgramFiles%\Python*).

- If it's installed but not on PATH, either add it, or re-run its installer
  and tick "Add python.exe to PATH".
- Otherwise install one:  winget install Python.Python.3.12
  (the Microsoft Store 'python' shim does NOT count - it only opens the Store).

Then re-run this script.
"@
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

# 4. Frontend .env - not committed to git, so create it from the template if
#    missing. Copied verbatim: the template already points at the local backend
#    (VITE_API_BASE_URL=http://localhost:8000, VITE_USE_MOCK_API=false), which is
#    what start.ps1 launches. Set VITE_USE_MOCK_API=true by hand only if you want
#    canned replies with no backend.
$envPath = Join-Path $frontendDir ".env"
$envExamplePath = Join-Path $frontendDir ".env.example"
if (-not (Test-Path $envPath)) {
    Step "Creating apps/frontend/.env from template (points at the local backend)..."
    Copy-Item $envExamplePath $envPath
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
#    IndicConformer-600M (CTC), run by the backend via sherpa-onnx (the wheel
#    is installed with the other Python packages in step 3 - prebuilt, no
#    compiler). One multilingual model covers Hindi/Marathi (English speech
#    input is handled on-device by the browser). The fp32 export (~470MB) is
#    used by default; int8 (~188MB) roughly doubles the word-error rate.
$indicDir    = Join-Path $backendDir "models\indicconformer"
$indicModel  = Join-Path $indicDir "model.onnx"
$indicTokens = Join-Path $indicDir "tokens.txt"
$indicBase   = "https://huggingface.co/meetsync/indic-conformer-onnx-sherpa/resolve/main"

if (-not (Test-Path $indicDir)) {
    New-Item -ItemType Directory -Force -Path $indicDir | Out-Null
}

if (-not (Test-ValidFile $indicModel (300MB))) {
    Step "Downloading IndicConformer-600M STT model (~470MB, one-time)..."
    Get-FileSafely "$indicBase/model.onnx?download=true" $indicModel
} else {
    Step "IndicConformer STT model already present - skipping download."
}

if (-not (Test-ValidFile $indicTokens 10000)) {
    Step "Downloading IndicConformer STT tokens..."
    Get-FileSafely "$indicBase/tokens.txt?download=true" $indicTokens
} else {
    Step "IndicConformer STT tokens already present - skipping."
}

# 6b. Offline English speech-to-text: Whisper base.en (int8) - handles
#     Indian-accented English well, so English STT is also fully offline (no
#     browser Web Speech / Google). Run through the same sherpa-onnx wheel.
$enSttName = "sherpa-onnx-whisper-base.en"
$enSttDir  = Join-Path $backendDir "models\stt\$enSttName"
$enSttArc  = Join-Path $backendDir "models\stt\$enSttName.tar.bz2"
$enSttUrl  = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$enSttName.tar.bz2"
if (-not (Get-ChildItem (Join-Path $enSttDir "*tokens.txt") -ErrorAction SilentlyContinue)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $backendDir "models\stt") | Out-Null
    Step "Downloading English STT model ($enSttName, ~145MB, one-time)..."
    Get-FileSafely $enSttUrl $enSttArc
    Step "Extracting English STT model..."
    & tar -xf $enSttArc -C (Join-Path $backendDir "models\stt")
    Remove-Item $enSttArc -ErrorAction SilentlyContinue
    # The tarball ships both fp32 and int8; we only load int8 - drop the ~290MB
    # of fp32 encoder/decoder.
    Get-ChildItem (Join-Path $enSttDir "*coder.onnx") -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike "*int8*" } | Remove-Item -Force
} else {
    Step "English STT model already present - skipping download."
}

# 7. Offline text-to-speech voice for non-English answers: a Piper VITS voice
#    (hi_IN-priyamvada, female), run by the backend through the same sherpa-onnx
#    wheel - no extra package. English answers use the browser's own voice.
$ttsName    = "vits-piper-hi_IN-priyamvada-medium"
$ttsDir     = Join-Path $backendDir "models\tts\$ttsName"
$ttsArchive = Join-Path $backendDir "models\tts\$ttsName.tar.bz2"
$ttsUrl     = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/$ttsName.tar.bz2"

if (-not (Test-Path (Join-Path $ttsDir "tokens.txt"))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $ttsDir) | Out-Null
    Step "Downloading Piper TTS voice ($ttsName, ~60MB, one-time)..."
    Get-FileSafely $ttsUrl $ttsArchive
    Step "Extracting Piper TTS voice..."
    & tar -xf $ttsArchive -C (Split-Path $ttsDir)
    Remove-Item $ttsArchive -ErrorAction SilentlyContinue
} else {
    Step "Piper TTS voice already present - skipping download."
}

$ollamaModel = Get-OllamaModel

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host ""
Write-Host "One prerequisite start.ps1 does NOT install for you:" -ForegroundColor Yellow
Write-Host "  Ollama must be installed and running, with the model pulled:" -ForegroundColor Yellow
Write-Host "    winget install Ollama.Ollama" -ForegroundColor Yellow
Write-Host "    ollama pull $ollamaModel   # OLLAMA_MODEL in apps\backend\.env" -ForegroundColor Yellow
Write-Host "  Without it the app still opens but replies show 'model unavailable'." -ForegroundColor DarkGray
Write-Host ""
Write-Host "Then: powershell -File scripts\start.ps1" -ForegroundColor Green
Write-Host "  (starts the backend, then opens the AI Tutor in a borderless window)"
