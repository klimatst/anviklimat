@echo off
setlocal
title KlimaEco — резервная копия базы
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"
if not defined XAMPP_HOME set "XAMPP_HOME=C:\xampp"
set "PHP_EXE=%XAMPP_HOME%\php\php.exe"
if not exist "%PHP_EXE%" (
  echo [ОШИБКА] Не найден PHP: "%PHP_EXE%"
  pause
  exit /b 1
)
if not exist "%APP_DIR%\maintenance\backup.php" (
  echo [ОШИБКА] Не найден maintenance\backup.php.
  pause
  exit /b 1
)
"%PHP_EXE%" "%APP_DIR%\maintenance\backup.php"
if errorlevel 1 (
  echo.
  echo Резервная копия не создана. Проверьте сообщение выше и конфигурацию БД.
  pause
  exit /b 1
)
echo.
echo Готово. SQL-файл сохранён в storage\backups.
pause
