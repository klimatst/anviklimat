@echo off
setlocal
chcp 65001 >nul
title KlimaEco — импорт каталога Hisense
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
  echo [ОШИБКА] Сайт ещё не установлен. Сначала запустите START-LOCAL.cmd и мастер установки.
  pause
  exit /b 1
)
"%PHP_EXE%" "maintenance\import-hisense.php"
if errorlevel 1 (
  echo.
  echo Импорт не завершён. Существующие данные не очищались.
  pause
  exit /b 1
)
echo.
echo Готово. Откройте каталог на сайте и проверьте модели.
pause
