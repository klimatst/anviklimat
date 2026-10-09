@echo off
setlocal EnableExtensions
title KlimaEco — локальный движок
rem Запускается из shared_hosting_php. Базу данных не удаляет и не пересоздаёт.
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"
if not defined XAMPP_HOME set "XAMPP_HOME=C:\xampp"
set "PHP_EXE=%XAMPP_HOME%\php\php.exe"
set "MYSQL_START=%XAMPP_HOME%\mysql_start.bat"
set "URL=http://127.0.0.1:4173/"

if not exist "%PHP_EXE%" (
  echo [ОШИБКА] Не найден PHP: "%PHP_EXE%"
  echo Установите XAMPP в C:\xampp либо задайте XAMPP_HOME.
  pause
  exit /b 1
)
if not exist "%APP_DIR%\index.php" (
  echo [ОШИБКА] Не найден index.php. Запустите скрипт из shared_hosting_php.
  pause
  exit /b 1
)
if not exist "%APP_DIR%\app\config.php" (
  echo [ПЕРВЫЙ ЗАПУСК] Откроется мастер установки; нужна база MySQL/MariaDB.
) else (
  echo [ГОТОВО] Конфигурация найдена; существующая база будет использована без сброса.
)
if exist "%MYSQL_START%" (
  tasklist /FI "IMAGENAME eq mysqld.exe" 2>nul | find /I "mysqld.exe" >nul
  if errorlevel 1 (
    echo Запускаю MariaDB из XAMPP...
    start "KlimaEco MariaDB" /min "%MYSQL_START%"
    timeout /t 4 /nobreak >nul
  )
) else (
  echo [ВНИМАНИЕ] Не найден mysql_start.bat. Предполагается, что MySQL/MariaDB уже запущена.
)
echo.
echo KlimaEco: %URL%
echo Остановка сервера: Ctrl+C в этом окне.
echo База данных не удаляется и не очищается этим скриптом.
start "" powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2; Start-Process '%URL%'"
cd /d "%APP_DIR%"
"%PHP_EXE%" -S 127.0.0.1:4173 -t "%APP_DIR%"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
echo Локальный сервер остановлен (код %EXIT_CODE%).
pause
exit /b %EXIT_CODE%
