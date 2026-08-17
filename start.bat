@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1

rem bakagateway Windows local launcher. It uses cmd.exe and project-local files only.

pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Cannot enter the bakagateway project directory.
  exit /b 1
)

set "CLOUDGATE_EXIT=0"
set "CLOUDGATE_MODE=start"
set "CLOUDGATE_PYTHON=%CD%\.venv\Scripts\python.exe"
set "CLOUDGATE_REQUIREMENTS=%CD%\requirements-dev.txt"
set "CLOUDGATE_WHEELHOUSE=%CD%\wheelhouse"

if /I "%~1"=="--check-only" (
  set "CLOUDGATE_MODE=check"
  shift
)
if /I "%~1"=="--create-admin" (
  set "CLOUDGATE_MODE=admin"
  shift
)
if not "%~1"=="" (
  echo [ERROR] Unknown option: %~1
  echo Usage: start.bat [--check-only ^| --create-admin]
  set "CLOUDGATE_EXIT=2"
  goto :finish
)

if not exist "%CD%\wsgi.py" (
  echo [ERROR] wsgi.py is missing.
  set "CLOUDGATE_EXIT=1"
  goto :finish
)
if not exist "%CLOUDGATE_REQUIREMENTS%" (
  echo [ERROR] requirements-dev.txt is missing.
  set "CLOUDGATE_EXIT=1"
  goto :finish
)

if not exist "%CLOUDGATE_PYTHON%" (
  echo [SETUP] Creating the bakagateway virtual environment...
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv ".venv"
  ) else (
    where python >nul 2>&1
    if errorlevel 1 (
      echo [ERROR] Python was not found. Install Python 3.12, 3.13, or 3.14.
      set "CLOUDGATE_EXIT=1"
      goto :finish
    )
    python -m venv ".venv"
  )
  if errorlevel 1 (
    echo [ERROR] The virtual environment could not be created.
    set "CLOUDGATE_EXIT=1"
    goto :finish
  )
)

"%CLOUDGATE_PYTHON%" -c "import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] < (3, 15) else 1)"
if errorlevel 1 (
  echo [ERROR] bakagateway requires Python 3.12, 3.13, or 3.14.
  set "CLOUDGATE_EXIT=1"
  goto :finish
)

"%CLOUDGATE_PYTHON%" -c "import cryptography, flask, flask_login, flask_migrate, flask_sqlalchemy, flask_wtf, png, qrcode, sqlalchemy" >nul 2>&1
if errorlevel 1 (
  if not exist "%CLOUDGATE_WHEELHOUSE%\*.whl" (
    echo [ERROR] Dependencies are missing and the local wheelhouse is empty.
    echo No network download was attempted.
    set "CLOUDGATE_EXIT=1"
    goto :finish
  )
  echo [SETUP] Installing dependencies from the local wheelhouse...
  "%CLOUDGATE_PYTHON%" -m pip install --disable-pip-version-check --no-index --find-links "%CLOUDGATE_WHEELHOUSE%" -r "%CLOUDGATE_REQUIREMENTS%"
  if errorlevel 1 (
    echo [ERROR] Local dependency installation failed.
    set "CLOUDGATE_EXIT=1"
    goto :finish
  )
)

"%CLOUDGATE_PYTHON%" -m pip check >nul
if errorlevel 1 (
  echo [ERROR] The local Python environment has broken packages.
  set "CLOUDGATE_EXIT=1"
  goto :finish
)

if not defined CLOUD_GATEWAY_ENV set "CLOUD_GATEWAY_ENV=local"
if not defined CLOUD_GATEWAY_HOST set "CLOUD_GATEWAY_HOST=127.0.0.1"
if not defined CLOUD_GATEWAY_PORT set "CLOUD_GATEWAY_PORT=5100"
set "FLASK_DEBUG=0"
set "PYTHONUTF8=1"

if /I not "%CLOUD_GATEWAY_ENV%"=="production" (
  if /I not "%CLOUD_GATEWAY_HOST%"=="127.0.0.1" (
    if /I not "%CLOUD_GATEWAY_HOST%"=="localhost" (
      if /I not "%CLOUD_GATEWAY_HOST%"=="::1" (
        echo [ERROR] Local mode can only listen on a loopback address.
        echo Use production mode with HTTPS when exposing bakagateway to a network.
        set "CLOUDGATE_EXIT=1"
        goto :finish
      )
    )
  )
)

echo.
echo [1/4] Applying bakagateway database migrations...
"%CLOUDGATE_PYTHON%" -m flask --app wsgi:app db upgrade
if errorlevel 1 (
  set "CLOUDGATE_EXIT=1"
  goto :finish
)

echo.
echo [2/4] Initializing built-in roles and permissions...
"%CLOUDGATE_PYTHON%" -m flask --app wsgi:app init-db
if errorlevel 1 (
  set "CLOUDGATE_EXIT=1"
  goto :finish
)

echo.
echo [3/4] Checking the bakagateway application...
"%CLOUDGATE_PYTHON%" -m flask --app wsgi:app routes >nul
if errorlevel 1 (
  set "CLOUDGATE_EXIT=1"
  goto :finish
)

echo.
echo [4/4] Purging expired email verification records...
"%CLOUDGATE_PYTHON%" -m flask --app wsgi:app purge-email-security
if errorlevel 1 (
  set "CLOUDGATE_EXIT=1"
  goto :finish
)

if "%CLOUDGATE_MODE%"=="check" (
  echo.
  echo [OK] bakagateway startup validation passed. The server was not started.
  goto :finish
)

if "%CLOUDGATE_MODE%"=="admin" (
  echo.
  echo [ADMIN] Creating a bakagateway administrator...
  "%CLOUDGATE_PYTHON%" -m flask --app wsgi:app create-admin
  set "CLOUDGATE_EXIT=%ERRORLEVEL%"
  goto :finish
)

echo.
echo [START] bakagateway v1.14.0
echo URL: http://%CLOUD_GATEWAY_HOST%:%CLOUD_GATEWAY_PORT%
echo Press Ctrl+C to stop the local server.
echo.
"%CLOUDGATE_PYTHON%" -m flask --app wsgi:app run --host "%CLOUD_GATEWAY_HOST%" --port "%CLOUD_GATEWAY_PORT%" --no-debugger --no-reload
set "CLOUDGATE_EXIT=%ERRORLEVEL%"

:finish
if not "%CLOUDGATE_EXIT%"=="0" (
  echo.
  echo [FAILED] bakagateway did not start. Review the message above.
  if not defined CLOUDGATE_NO_PAUSE pause
)
popd >nul 2>&1
endlocal & exit /b %CLOUDGATE_EXIT%
