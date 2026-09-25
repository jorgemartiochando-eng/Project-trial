@echo off
REM Called by start.bat: prepares Python, installs libraries when needed, starts the app.
cd /d "%~dp0.."

REM 2) Python environment: create it the first time, rebuild it if it is broken
if not exist ".venv\Scripts\python.exe" goto makevenv
".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 goto makevenv
goto deps

:makevenv
echo  Setting up Python (first time only, about 1 minute)...
if exist ".venv" rmdir /s /q ".venv"
py -3.12 -m venv .venv >nul 2>&1
if not exist ".venv\Scripts\python.exe" py -m venv .venv >nul 2>&1
if not exist ".venv\Scripts\python.exe" python -m venv .venv >nul 2>&1
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  Python was not found. Install it from https://www.python.org/downloads/ and try again.
  pause
  exit /b 1
)

:deps
REM 3) Install libraries only when requirements.txt has changed since the last install
fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>&1
if errorlevel 1 (
  echo  Installing libraries...
  ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo  Installing libraries failed - see the messages above.
    pause
    exit /b 1
  )
  copy /y requirements.txt ".venv\installed-requirements.txt" >nul
)

REM 4) Open the browser a few seconds after the server starts
start "" /b cmd /c "ping -n 5 127.0.0.1 >nul & start http://localhost:8000"
echo.
echo  Running at http://localhost:8000  -  close this window to stop the app.
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app
pause
