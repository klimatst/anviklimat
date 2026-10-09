@echo off
setlocal
cd /d "%~dp0"

where node >nul 2>&1
if errorlevel 1 (
  echo ОШИБКА: Node.js не установлен или не добавлен в PATH.
  echo Установите LTS: https://nodejs.org/
  pause
  exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
  echo ВНИМАНИЕ: Git не найден. Сайт откроется из локальных файлов, но синхронизация с GitHub работать не будет.
  echo Установите Git: https://git-scm.com/download/win
  echo.
)

echo.
echo ============================================
echo  KlimaEco — локальный просмотр репозитория
echo  Адрес: http://localhost:4173
echo  Синхронизация GitHub: /api/sync
echo  Остановка: Ctrl+C
echo ============================================
echo.

start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:4173'"
node server.mjs
