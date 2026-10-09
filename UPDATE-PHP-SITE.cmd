@echo off
setlocal
chcp 65001 >nul
title KlimaEco — обновление PHP-сайта
set "REPO_ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$script=Join-Path $env:TEMP 'klimaeco-update-php-site.ps1'; try { Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/klimatst/anviklimat/master/tools/update-php-site.ps1' -OutFile $script; & $script -RepoRoot '%REPO_ROOT%' } catch { Write-Host ('[ОШИБКА] Не удалось загрузить проверку обновления: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }"
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
