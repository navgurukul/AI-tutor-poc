<#
.SYNOPSIS
  Puts an "AI Tutor" shortcut with the app icon on the Windows desktop, so the
  whole stack (backend + frontend + borderless window) starts with one
  double-click instead of a PowerShell command.

.USAGE
  From the repo root:  powershell -File scripts\create-shortcut.ps1

  Options:
    -StartMenu        also add it to the Start Menu (searchable by name)
    -Destination <p>  put the .lnk somewhere else instead of the desktop

  Run scripts\setup.ps1 first - the shortcut runs scripts\start.ps1, which
  needs the dependencies setup installs. Re-run this script after moving the
  repo: the shortcut stores an absolute path to it.
#>
param(
    [string]$Destination,
    [switch]$StartMenu
)

$ErrorActionPreference = "Stop"

$repoRoot   = Split-Path -Parent $PSScriptRoot
$startPs1   = Join-Path $repoRoot "scripts\start.ps1"
$iconPath   = Join-Path $repoRoot "apps\desktop\assets\AI-Tutor.ico"
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path $startPs1)) { throw "Cannot find $startPs1" }
if (-not (Test-Path $iconPath)) {
    throw "Icon not found at $iconPath. Regenerate it on a Mac/Linux box with: node scripts/generate-icons.mjs"
}

if ($Destination) {
    if (-not (Test-Path $Destination)) { throw "Destination folder does not exist: $Destination" }
    $targets = @($Destination)
} else {
    # GetFolderPath rather than "$env:USERPROFILE\Desktop": it follows a
    # redirected/OneDrive-backed Desktop, which is where the icon actually has
    # to land on a lot of Windows installs.
    $targets = @([Environment]::GetFolderPath("Desktop"))
}
if ($StartMenu) {
    $startMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "AI Tutor"
    New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
    $targets += $startMenuDir
}

$shell = New-Object -ComObject WScript.Shell

foreach ($dir in $targets) {
    $linkPath = Join-Path $dir "AI Tutor.lnk"

    # Only replace a shortcut that points at this repo's start.ps1. A .lnk of
    # the same name aimed anywhere else belongs to something we didn't create.
    if (Test-Path $linkPath) {
        $existingArgs = $shell.CreateShortcut($linkPath).Arguments
        if ($existingArgs -notlike "*start.ps1*") {
            throw "Refusing to overwrite $linkPath - it isn't a shortcut this script created. Move it aside first."
        }
    }

    $shortcut = $shell.CreateShortcut($linkPath)
    $shortcut.TargetPath = $powershell
    # -ExecutionPolicy Bypass because the default Restricted/AllSigned policy
    # blocks unsigned local scripts, which is exactly what start.ps1 is.
    $shortcut.Arguments        = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$startPs1`""
    $shortcut.WorkingDirectory = $repoRoot
    $shortcut.IconLocation     = "$iconPath,0"
    $shortcut.Description      = "Start the offline AI Tutor (backend, frontend and tutor window)"
    # 7 = minimised. The console has to exist - it's what start.ps1 writes
    # progress to and what Ctrl+C stops the stack from - but it belongs in the
    # taskbar, not on top of the tutor window it just opened.
    $shortcut.WindowStyle = 7
    $shortcut.Save()

    Write-Host "Created: $linkPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "Double-click it to start the backend, the frontend and the tutor window." -ForegroundColor Green
Write-Host "The minimised PowerShell window in the taskbar holds the stack open - closing it, or Ctrl+C in it, stops everything."
