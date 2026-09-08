@echo off
REM Core latency numbers for this device. The AI Tutor must be running.
setlocal
set PY=%~dp0..\runtime\python\python.exe
if not exist "%PY%" set PY=python
"%PY%" "%~dp0benchmark.py" %*
echo.
pause
