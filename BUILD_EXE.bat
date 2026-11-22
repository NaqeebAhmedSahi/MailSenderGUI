@echo off
setlocal

rem ==========================================================
rem  MailFlow Pro - one-click Windows build
rem  Result: MailFlowPro.exe (single file, share only this)
rem          MailFlowPro.zip (same exe, zipped for sending)
rem ==========================================================

cd /d "%~dp0"

echo.
echo  MailFlow Pro - building single-file Windows EXE
echo  ===============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo and tick "Add Python to PATH" during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :fail
) else (
    echo [1/4] Using existing virtual environment.
)

echo [2/4] Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt pillow
if errorlevel 1 goto :fail

echo [3/4] Building EXE (this takes a few minutes)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean mail-sender-gui.spec
if errorlevel 1 goto :fail

echo [4/4] Packaging...
copy /y "dist\mail-sender-gui.exe" "MailFlowPro.exe" >nul
if errorlevel 1 goto :fail
if exist "MailFlowPro.zip" del /q "MailFlowPro.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'MailFlowPro.exe' -DestinationPath 'MailFlowPro.zip' -Force"

echo.
echo  DONE.
echo    %~dp0MailFlowPro.exe
echo    %~dp0MailFlowPro.zip
echo.
echo  Send your friend ONLY MailFlowPro.exe (or the zip). Nothing else is needed.
echo.
pause
exit /b 0

:fail
echo.
echo  BUILD FAILED - see the messages above.
pause
exit /b 1
