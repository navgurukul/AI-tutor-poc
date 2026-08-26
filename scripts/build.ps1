<#
.SYNOPSIS
  Builds the frontend for production (apps/frontend/dist).

.USAGE
  From the repo root:  powershell -File scripts\build.ps1

  Run scripts\setup.ps1 first if you haven't yet (dependencies + voice model
  files need to exist). apps\desktop's `npm start` will also build
  automatically if dist/ is missing, so this script is only needed if you
  want to build ahead of time or rebuild after code changes.
#>

$ErrorActionPreference = "Stop"

$repoRoot    = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot "apps\frontend"

Write-Host "==> Building frontend for production..." -ForegroundColor Cyan
Push-Location $frontendDir
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Build failed" }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Build complete: apps\frontend\dist" -ForegroundColor Green
Write-Host "Next: cd apps\desktop; npm start"
