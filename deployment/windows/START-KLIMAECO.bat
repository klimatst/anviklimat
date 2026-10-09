@echo off
setlocal
cd /d "%~dp0\..\.."
title KlimaEco - quick setup
echo ==========================================
echo        KLIMAECO - START / INSTALL
echo ==========================================
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo Python not found. Install Python 3.11+ from https://www.python.org/downloads/
  echo During installation tick "Add Python to PATH".
  pause
  exit /b 1
)
where java >nul 2>nul
if errorlevel 1 (
  echo Java not found. Install Java 17 from https://adoptium.net/
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Check the message above.
  pause
  exit /b 1
)
pause
