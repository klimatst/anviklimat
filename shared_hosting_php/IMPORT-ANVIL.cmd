@echo off
setlocal EnableExtensions
chcp 65001 >nul
title KlimaEco — перенос данных из Anvil
cd /d "%~dp0"
set "PHP_EXE="
if defined XAMPP_HOME if exist "%XAMPP_HOME%\php\php.exe" set "PHP_EXE=%XAMPP_HOME%\php\php.exe"
if not defined PHP_EXE if exist "C:\xampp\php\php.exe" set "PHP_EXE=C:\xampp\php\php.exe"
if not defined PHP_EXE if exist "C:\tools\xampp\php\php.exe" set "PHP_EXE=C:\tools\xampp\php\php.exe"
if not defined PHP_EXE for %%P in (php.exe) do set "PHP_EXE=%%~$PATH:P"
if not defined PHP_EXE (
  echo [ОШИБКА] Не найден PHP. Укажите XAMPP_HOME или добавьте php.exe в PATH.
  pause
  exit /b 1
)
if not exist "app\config.php" (
  echo [ОШИБКА] Сначала запустите START-LOCAL.cmd и завершите установку сайта.
  pause
  exit /b 1
)
if not exist "storage\imports\anvil-export.json.gz" (
  echo [ОШИБКА] Файл экспорта не найден.
  echo Скопируйте его из Anvil в storage\imports\anvil-export.json.gz.
  pause
  exit /b 1
)
"%PHP_EXE%" "maintenance\import-anvil.php"
if errorlevel 1 (
  echo.
  echo Импорт не выполнен. Исходный файл оставлен на месте.
  pause
  exit /b 1
)
echo.
echo Данные перенесены. Файл содержит персональные сведения — удалите его из storage\imports после проверки.
pause
endlocal
