<#
.SYNOPSIS
  Starts the full AI Tutor stack: the backend (FastAPI/uvicorn) in the
  background, then the desktop app, which starts the frontend and opens it
  in a borderless window.

.USAGE
  From the repo root:  powershell -File scripts\start.ps1
  Run scripts\setup.ps1 first if you haven't (installs dependencies for all
  three apps and creates their .env files).

  Requires Ollama running locally (`ollama serve`) with the model pulled
  (`ollama pull qwen2.5:1.5b`) - the backend starts without it, but /health
  will report degraded and chat requests will fail until it's reachable.

  Closing the borderless window, or Ctrl+C here, stops both the frontend and
  the backend.
#>

$ErrorActionPreference = "Stop"

# The venv's python.exe on this machine is a launcher stub that re-execs the
# real interpreter as a child process, so the PID Start-Process hands back
# isn't reliably the one holding the port. Killing by the port's listener
# instead of that PID is what actually frees it - same reasoning as backend
# port cleanup anywhere else.
function Stop-ProcessOnPort($port) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $conns) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

$repoRoot      = Split-Path -Parent $PSScriptRoot
$backendDir    = Join-Path $repoRoot "apps\backend"
$desktopDir    = Join-Path $repoRoot "apps\desktop"
$backendPython = Join-Path $backendDir ".venv\Scripts\python.exe"
$backendOutLog = Join-Path $repoRoot "backend.out.log"
$backendErrLog = Join-Path $repoRoot "backend.err.log"

if (-not (Test-Path $backendPython)) {
    throw "Backend virtualenv not found at $backendPython. Run scripts\setup.ps1 first."
}

# Invoke-WebRequest uses WinINet, which has been observed to hang/timeout here
# when this script runs as a background/non-interactive process even though
# the same URL answers instantly - curl.exe doesn't go through WinINet and has
# been reliable in that same situation, so it's used for every readiness check
# below instead.
function Test-UrlOk($url) {
    curl.exe -sf --max-time 2 $url *> $null
    return $LASTEXITCODE -eq 0
}

Write-Host ""
Write-Host "==> Checking Ollama..." -ForegroundColor Cyan
if (Test-UrlOk "http://localhost:11434/api/version") {
    Write-Host "Ollama is up." -ForegroundColor Green
} else {
    Write-Host "Ollama isn't responding on http://localhost:11434 - start it with 'ollama serve' in another terminal (and 'ollama pull qwen2.5:1.5b' if you haven't). Continuing anyway; /health will report degraded until it's reachable." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==> Starting backend on http://localhost:8000 ..." -ForegroundColor Cyan
Start-Process -FilePath $backendPython `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" `
    -WorkingDirectory $backendDir `
    -RedirectStandardOutput $backendOutLog -RedirectStandardError $backendErrLog `
    -WindowStyle Hidden | Out-Null

try {
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-UrlOk "http://localhost:8000/health") {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) {
        throw "Backend did not become healthy within 30s. Check $backendErrLog"
    }
    Write-Host "Backend ready. Logs: $backendOutLog / $backendErrLog" -ForegroundColor Green

    Write-Host ""
    Write-Host "==> Starting desktop app (frontend + borderless window)..." -ForegroundColor Cyan
    # Dev mode (Vite dev server, always fresh) rather than `npm start`'s
    # production build+preview - launch.mjs only rebuilds dist/ when it's
    # missing, not when it's stale, so production mode can silently serve
    # old code. Use `npm start` yourself once you want the packaged build.
    Push-Location $desktopDir
    try {
        npm run dev
    } finally {
        Pop-Location
    }
} finally {
    Write-Host ""
    Write-Host "==> Stopping backend..." -ForegroundColor Cyan
    Stop-ProcessOnPort 8000
}
