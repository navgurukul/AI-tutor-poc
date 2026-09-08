<#
.SYNOPSIS
  Starts the AI Tutor: vendored Ollama, the backend, and the tutor window.

.DESCRIPTION
  Replaces scripts/start.ps1 plus the Node/Vite launcher. There is no Node
  here and no Vite: the backend serves the built frontend itself, so one
  process holds the whole app and the browser talks to its own origin.

  Every setting is injected as an environment variable rather than read from a
  .env file. pydantic-settings ranks real environment variables above dotenv
  values, so this is the single source of truth on a device and there is no
  template that can drift away from the code defaults.

  This is the ENGLISH-ONLY build: speech is browser-side in both directions, so
  no speech model paths are set and none ship.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "",
    [string]$DataRoot    = "$env:ProgramData\AITutor",
    [int]$Port           = 8756,
    [int]$OllamaPort     = 11435,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

# $PSScriptRoot is EMPTY while param() defaults are evaluated -- it is only
# populated once the script body runs -- so the script's own location has to be
# resolved here rather than in the param block above.
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } elseif ($PSCommandPath) { Split-Path -Parent $PSCommandPath } else { (Get-Location).Path }
if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $scriptDir }

$logDir = Join-Path $DataRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
function Log($m) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m"
    Add-Content -Path (Join-Path $logDir "launcher.log") -Value $line
    Write-Host $line
}

# --- single instance -------------------------------------------------------
# Closing the tutor window deliberately leaves the stack up, so the next
# double-click is instant. Without this guard that second click would start a
# second Ollama and a second 2.8 GB model load.
$mutex = New-Object System.Threading.Mutex($false, "Local\AITutor.Launcher")
if (-not $mutex.WaitOne(0)) {
    Log "Already running - reopening the window."
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/" }
    exit 0
}

$python  = Join-Path $InstallRoot "runtime\python\python.exe"
$ollama  = Join-Path $InstallRoot "runtime\ollama\ollama.exe"
$appDir  = Join-Path $DataRoot "app\current\backend"
$webDir  = Join-Path $DataRoot "app\current\web"
$dbPath  = Join-Path $DataRoot "content\current\library.db"
$models  = Join-Path $InstallRoot "runtime\models"

foreach ($p in @($python, $ollama, $appDir)) {
    if (-not (Test-Path $p)) { throw "Missing $p - the install is incomplete. Re-run install.ps1." }
}

function Test-Url($url) {
    # curl.exe, not Invoke-WebRequest: IWR goes through WinINet, which has been
    # observed to hang for a non-interactive process even when the same URL
    # answers instantly. curl.exe is in-box on Windows 10+ and does not.
    & curl.exe -sf --max-time 2 $url *> $null
    return $LASTEXITCODE -eq 0
}

$script:children = @()

# --- Ollama ----------------------------------------------------------------
# Port 11435, not 11434: a machine that once had the official Ollama installed
# would otherwise collide with us, and the official build self-updates.
if (Test-Url "http://127.0.0.1:$OllamaPort/api/version") {
    Log "Ollama already up on $OllamaPort - reusing."
} else {
    Log "Starting vendored Ollama on 127.0.0.1:$OllamaPort"
    $env:OLLAMA_HOST              = "127.0.0.1:$OllamaPort"
    $env:OLLAMA_MODELS            = Join-Path $models "ollama"
    $env:OLLAMA_KEEP_ALIVE        = "-1"      # never unload; a reload costs a student ~2s every pause
    $env:OLLAMA_MAX_LOADED_MODELS = "2"       # gemma2:2b and bge-m3 both resident
    $env:OLLAMA_NUM_PARALLEL      = "1"
    $env:OLLAMA_NOPRUNE           = "1"       # our model dir is read-only; do not try to prune it
    $env:OLLAMA_ORIGINS           = ""        # nothing browser-side talks to Ollama
    $env:HOME                     = Join-Path $DataRoot "state\ollama-home"
    New-Item -ItemType Directory -Force -Path $env:HOME | Out-Null
    $script:children += (Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logDir "ollama.out.log") `
        -RedirectStandardError  (Join-Path $logDir "ollama.err.log"))
    for ($i = 0; $i -lt 60; $i++) {
        if (Test-Url "http://127.0.0.1:$OllamaPort/api/version") { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-Url "http://127.0.0.1:$OllamaPort/api/version")) { throw "Ollama did not start. See $logDir\ollama.err.log" }
}

# --- backend ---------------------------------------------------------------
Log "Starting backend on 127.0.0.1:$Port"

$env:PYTHONPATH             = Join-Path $InstallRoot "runtime\python\Lib\site-packages"
$env:PYTHONUTF8             = "1"          # Devanagari in paths and logs
$env:PYTHONDONTWRITEBYTECODE= "1"          # app dir is Users-writable; no .pyc litter

$env:PACKAGED               = "true"       # loopback guards on, /docs off
$env:BIND_HOST              = "127.0.0.1"
$env:BIND_PORT              = "$Port"
$env:CORS_ORIGINS           = ""           # same-origin; middleware not added at all
$env:WEB_DIR                = $webDir
# Per-turn latency CSVs land beside the other logs, so a slow device can be
# analysed after the fact instead of only while someone watches a console.
$env:AITUTOR_LOG_DIR        = $logDir
$env:TURN_LOG_ENABLED       = "true"

# Reassigned deliberately: the Ollama server above wanted a bare host:port to
# bind, while the backend's ollama_host setting wants a URL to call. Ollama
# already captured its value when it was spawned, so overwriting is safe.
$env:OLLAMA_HOST            = "http://127.0.0.1:$OllamaPort"
$env:OLLAMA_MODEL           = "qwen2.5:1.5b"
$env:NUM_CTX                = "4096"

# No STT_MODEL_DIR / TTS_MODEL_DIR: this is the English-only build, where
# speech is entirely browser-side (Web Speech API in, speechSynthesis out) and
# the backend has no stt.py or tts.py to point at a model.

$env:RAG_DB_PATH            = $dbPath
$env:RAG_ENABLED            = if (Test-Path $dbPath) { "true" } else { "false" }

$backend = Start-Process $python -ArgumentList "-m","app.serve" -WorkingDirectory $appDir `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir "backend.out.log") `
    -RedirectStandardError  (Join-Path $logDir "backend.err.log")
$script:children += $backend

try {
    # 90s: no acoustic model to load here, only qwen2.5:1.5b warming in the
    # background, and /health answers before that finishes.
    $ready = $false
    for ($i = 0; $i -lt 90; $i++) {
        if (Test-Url "http://127.0.0.1:$Port/health") { $ready = $true; break }
        if ($backend.HasExited) { throw "Backend exited with code $($backend.ExitCode). See $logDir\backend.err.log" }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "Backend did not become healthy in 90s. See $logDir\backend.err.log" }
    Log "Backend ready on http://127.0.0.1:$Port/"

    Set-Content -Path (Join-Path $DataRoot "state\session.json") -Encoding UTF8 -Value (
        @{ port = $Port; pid = $backend.Id; started_utc = (Get-Date).ToUniversalTime().ToString("s") } | ConvertTo-Json)

    # --- the tutor window --------------------------------------------------
    if (-not $NoBrowser) {
        $candidates = @(
            "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
            "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
            "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
        )
        $browser = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
        if ($browser) {
            Log "Opening tutor window via $browser"
            # --profile-directory, NOT --user-data-dir. A separate user-data
            # root would isolate Chrome's installation-level component
            # downloads -- including the on-device speech model -- so English
            # speech input would silently fall back to sending audio to Google,
            # which fails outright at an offline site. A named profile inside
            # the default root inherits those downloads.
            Start-Process $browser -ArgumentList @(
                "--app=http://127.0.0.1:$Port/",
                "--new-window", "--window-size=1280,800",
                "--profile-directory=AI Tutor",
                "--no-first-run", "--no-default-browser-check", "--disable-extensions"
            )
        } else {
            Log "No Chrome or Edge found; opening the default browser instead."
            Start-Process "http://127.0.0.1:$Port/"
        }
    }

    Log "Running. Close this window to stop the AI Tutor."
    while (-not $backend.HasExited) { Start-Sleep -Seconds 2 }
    Log "Backend exited with code $($backend.ExitCode)."
}
finally {
    Log "Shutting down."
    foreach ($c in $script:children) {
        if ($c -and -not $c.HasExited) { Stop-Process -Id $c.Id -Force -ErrorAction SilentlyContinue }
    }
    Remove-Item (Join-Path $DataRoot "state\session.json") -ErrorAction SilentlyContinue
    $mutex.ReleaseMutex(); $mutex.Dispose()
}
