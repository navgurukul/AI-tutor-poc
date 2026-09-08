@echo off
REM Thin shim so the Start Menu / Desktop shortcut has a stable, quoted target
REM that does not depend on the machine's PowerShell execution policy.
setlocal
start "" /min powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1" %*
endlocal
