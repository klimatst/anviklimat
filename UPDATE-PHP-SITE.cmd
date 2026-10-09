@echo off
setlocal
chcp 65001 >nul
title KlimaEco — обновление PHP-сайта
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\update-php-site.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo Обновление не выполнено. Файлы не сбрасывались и не удалялись.
) else (
  echo Готово. Обновите страницу http://127.0.0.1:4173/ сочетанием Ctrl+F5.
)
echo.
pause
exit /b %RESULT%
