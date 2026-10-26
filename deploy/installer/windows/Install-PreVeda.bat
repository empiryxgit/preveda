@echo off
cd /d "%~dp0"
echo Starting the PreVeda Madhu-DR installer...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
