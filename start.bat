@echo off
title Pay Transparency Engine
REM Double-click this file to update and start the app. Close the window to stop it.
REM Kept deliberately small so an update never changes it while it runs;
REM the real work is in scripts\launch.bat.
cd /d "%~dp0"

echo.
echo  Pay Transparency Engine
echo  -----------------------

REM Get the latest version (skipped if Git is missing or there is no internet)
where git >nul 2>&1
if not errorlevel 1 (
  echo  Checking for updates...
  git pull --quiet
  if errorlevel 1 echo  Could not update - starting the version you already have.
)

call "%~dp0scripts\launch.bat"
