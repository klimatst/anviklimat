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

set "BIND_HOST=127.0.0.1"
set "LAN_IP="
choice /C 12 /N /T 12 /D 1 /M "Запускать только на этом компьютере (1) или открыть доступ в локальной сети (2)? [1] "
if errorlevel 2 set "BIND_HOST=0.0.0.0"
if "%BIND_HOST%"=="0.0.0.0" for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred | Where-Object { $_.IPAddress -notlike '127.*' -and $_.InterfaceAlias -notmatch 'Loopback' } | Select-Object -First 1 -ExpandProperty IPAddress"`) do set "LAN_IP=%%I"
if "%BIND_HOST%"=="0.0.0.0" if not defined LAN_IP (
  echo [ВНИМАНИЕ] Не удалось определить IPv4-адрес локальной сети. Запускаю только на этом компьютере.
  set "BIND_HOST=127.0.0.1"
)

set "OPEN_URL=http://127.0.0.1:4173/"

echo.
if "%BIND_HOST%"=="0.0.0.0" (
  echo KlimaEco открыт в локальной сети.
  echo На этом компьютере: http://127.0.0.1:4173/
  echo С других устройств: http://%LAN_IP%:4173/
  echo Разрешите входящие подключения к PHP в брандмауэре Windows для частной сети.
) else (
  echo KlimaEco доступен только на этом компьютере.
)
echo Адрес: %OPEN_URL%
echo При первом открытии сайт автоматически создаст базу и заполнит стартовые данные.
echo Для остановки нажмите Ctrl+C в этом окне.
echo.
start "" "%OPEN_URL%"
"%PHP_EXE%" -S %BIND_HOST%:4173 -t "%~dp0" "%~dp0router.php"
if errorlevel 1 (
  echo.
  echo Сервер остановлен с ошибкой. Возможно, порт 4173 уже занят.
  pause
)
endlocal
