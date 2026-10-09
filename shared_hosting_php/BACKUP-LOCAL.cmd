@echo off
setlocal
chcp 65001 >nul
title KlimaEco — резервная копия базы
cd /d "%~dp0"
set "PHP_EXE="
if defined XAMPP_HOME if exist "%XAMPP_HOME%\php\php.exe" set "PHP_EXE=%XAMPP_HOME%\php\php.exe"
if not defined PHP_EXE if exist "C:\xampp\php\php.exe" set "PHP_EXE=C:\xampp\php\php.exe"
if not defined PHP_EXE for %%P in (php.exe) do set "PHP_EXE=%%~$PATH:P"
if not defined PHP_EXE (
  echo [ОШИБКА] Не найден PHP. Укажите XAMPP_HOME или добавьте php.exe в PATH.
  pause
  exit /b 1
)
"%PHP_EXE%" "maintenance\backup.php"
if errorlevel 1 (
  echo.
  echo Резервная копия не создана. Проверьте сообщение выше и конфигурацию БД.
  pause
  exit /b 1
)
echo.
echo Резервная копия находится в storage\backups.
pause
