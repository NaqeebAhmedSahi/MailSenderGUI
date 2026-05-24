@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo MailFlow Pro - Windows Build
echo ============================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    echo Install Python 3.9+ from https://www.python.org/downloads/
    echo Enable "Add Python to PATH" during installation.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 exit /b 1
)

call .venv\Scripts\activate.bat
if errorlevel 1 exit /b 1

python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 exit /b 1

python build.py
if errorlevel 1 exit /b 1

echo.
echo Done. Double-click dist\mail-sender-gui.exe to run the app.
echo.

endlocal
