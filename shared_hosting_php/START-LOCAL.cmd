@echo off
setlocal EnableExtensions
chcp 65001 >nul
title KlimaEco — локальный движок

cd /d "%~dp0"
set "PHP_EXE="

if defined XAMPP_HOME if exist "%XAMPP_HOME%\php\php.exe" set "PHP_EXE=%XAMPP_HOME%\php\php.exe"
if not defined PHP_EXE if exist "C:\xampp\php\php.exe" (
  set "XAMPP_HOME=C:\xampp"
  set "PHP_EXE=C:\xampp\php\php.exe"
)
if not defined PHP_EXE if exist "C:\tools\xampp\php\php.exe" (
  set "XAMPP_HOME=C:\tools\xampp"
  set "PHP_EXE=C:\tools\xampp\php\php.exe"
)
if not defined PHP_EXE for %%P in (php.exe) do set "PHP_EXE=%%~$PATH:P"

if not defined PHP_EXE (
  echo [ОШИБКА] Не найден PHP.
  echo Установите XAMPP в C:\xampp или добавьте php.exe в PATH.
  pause
  exit /b 1
)
if not exist "%PHP_EXE%" (
  echo [ОШИБКА] PHP не найден: "%PHP_EXE%"
  pause
  exit /b 1
)

"%PHP_EXE%" -r "exit(extension_loaded('pdo_mysql') ? 0 : 1);"
if errorlevel 1 (
  echo [ОШИБКА] В выбранном PHP не включено расширение pdo_mysql.
  echo Для XAMPP используйте PHP из папки XAMPP.
  pause
  exit /b 1
)

if defined XAMPP_HOME if exist "%XAMPP_HOME%\mysql\bin\mysqladmin.exe" (
  "%XAMPP_HOME%\mysql\bin\mysqladmin.exe" -h 127.0.0.1 -u root ping >nul 2>&1
  if errorlevel 1 (
    if exist "%XAMPP_HOME%\mysql_start.bat" (
      echo Запускаю MariaDB из XAMPP...
      start "KlimaEco MariaDB" /min cmd /c ""%XAMPP_HOME%\mysql_start.bat""
      for /L %%I in (1,1,20) do (
        "%XAMPP_HOME%\mysql\bin\mysqladmin.exe" -h 127.0.0.1 -u root ping >nul 2>&1
        if not errorlevel 1 goto database_ready
        timeout /t 1 /nobreak >nul
      )
      echo [ВНИМАНИЕ] MariaDB не подтвердила запуск за 20 секунд.
      echo Проверьте XAMPP Control Panel и журнал MySQL.
    )
  )
)
:database_ready

if exist "app\config.php" (
  echo Проверяю схему локальной базы данных...
  "%PHP_EXE%" "maintenance\upgrade.php"
  if errorlevel 1 (
    echo [ОШИБКА] Не удалось подготовить схему. Существующие данные не удалялись.
    pause
    exit /b 1
  )
  set "OPEN_URL=http://127.0.0.1:4173/"
) else (
  set "OPEN_URL=http://127.0.0.1:4173/install/"
)

echo.
echo KlimaEco запускается только на этом компьютере.
echo Адрес: %OPEN_URL%
echo Для остановки нажмите Ctrl+C в этом окне.
echo.
start "" "%OPEN_URL%"
"%PHP_EXE%" -S 127.0.0.1:4173 -t "%~dp0"
if errorlevel 1 (
  echo.
  echo Сервер остановлен с ошибкой. Возможно, порт 4173 уже занят.
  pause
)
endlocal
