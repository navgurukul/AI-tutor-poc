<#
.SYNOPSIS
  Removes the AI Tutor. Keeps the textbook corpus and logs unless -Purge.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = "",
    [string]$DataRoot    = "$env:ProgramData\AITutor",
    [switch]$Purge
)
$ErrorActionPreference = "Stop"

# $PSScriptRoot is EMPTY while param() defaults are evaluated -- it is only
# populated once the script body runs -- so the script's own location has to be
# resolved here rather than in the param block above.
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } elseif ($PSCommandPath) { Split-Path -Parent $PSCommandPath } else { (Get-Location).Path }
if (-not $InstallRoot) { $InstallRoot = Split-Path -Parent $scriptDir }

$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this elevated (Administrator)."
}

Write-Host "==> Stopping AI Tutor" -ForegroundColor Cyan
Get-Process -Name "ollama" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "$InstallRoot*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -like "$InstallRoot*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Write-Host "==> Removing shortcuts" -ForegroundColor Cyan
foreach ($d in @("$env:PUBLIC\Desktop", "$env:ProgramData\Microsoft\Windows\Start Menu\Programs")) {
    Remove-Item (Join-Path $d "AI Tutor.lnk") -Force -ErrorAction SilentlyContinue
}

Write-Host "==> Removing $InstallRoot" -ForegroundColor Cyan
Remove-Item $InstallRoot -Recurse -Force -ErrorAction SilentlyContinue

if ($Purge) {
    Write-Host "==> Purging $DataRoot (corpus and logs included)" -ForegroundColor Yellow
    Remove-Item $DataRoot -Recurse -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "==> Keeping $DataRoot (corpus, logs, state). Use -Purge to remove it." -ForegroundColor DarkGray
}
Write-Host "`nAI Tutor removed." -ForegroundColor Green
