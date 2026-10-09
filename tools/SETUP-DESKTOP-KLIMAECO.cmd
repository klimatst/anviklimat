@echo off
setlocal
cd /d "%~dp0\.."
where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git for Windows is required. Install from https://git-scm.com/download/win
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-desktop-klimaeco.ps1"
if errorlevel 1 pause
