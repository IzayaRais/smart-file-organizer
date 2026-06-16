@echo off
:: ================================================================
::  organize.bat  v3.1 — Launcher for organizer.py
::  - Checks Python is installed
::  - Auto-installs send2trash (Recycle Bin support)
::  - Passes folder path to Python engine
::  - Supports Organization by Type, Date, and Size
::  - Cleans up empty folders automatically
::  - Window stays open to show final report
:: ================================================================
setlocal EnableDelayedExpansion
title File Organizer v3.1
color 0A

echo.
echo  ============================================================
echo   FILE ORGANIZER v3.1  ^|  Type/Date/Size + Cleanup + Safe
echo  ============================================================
echo.

:: ── Locate organizer.py next to this .bat ───────────────────────
set "SCRIPT_DIR=%~dp0"
set "PY_SCRIPT=%SCRIPT_DIR%organizer.py"

if not exist "%PY_SCRIPT%" (
    echo  [ERROR] organizer.py not found in the same folder as this .bat file.
    echo.
    echo  Make sure both files are together:
    echo    organize.bat
    echo    organizer.py
    echo.
    pause
    exit /b 1
)

:: ── Check Python ────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed or not in your PATH.
    echo.
    echo  Download from: https://www.python.org/downloads/
    echo  IMPORTANT: During install, check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo  Python: %PYVER%

:: ── Auto-install send2trash (needed for Recycle Bin support) ────
echo  Checking send2trash...
python -c "import send2trash" >nul 2>&1
if errorlevel 1 (
    echo  Installing send2trash for Recycle Bin support...
    python -m pip install send2trash --quiet
    if errorlevel 1 (
        echo  [WARNING] Could not install send2trash.
        echo  Duplicates will be permanently deleted instead of recycled.
    ) else (
        echo  send2trash installed OK.
    )
) else (
    echo  send2trash: OK
)
echo.

:: ── Prompt for folder path ──────────────────────────────────────
set "FOLDER=%~1"
if "!FOLDER!"=="" (
    echo  Enter the full path of the folder to organize.
    echo  Tip: You can drag and drop the folder into this window.
    echo.
    set /p "FOLDER=  Folder path: "
)
set "FOLDER=%FOLDER:"=%"

if "!FOLDER!"=="" (
    echo.
    echo  [ERROR] No path entered.
    pause
    exit /b 1
)

if not exist "!FOLDER!\" (
    echo.
    echo  [ERROR] Folder not found: !FOLDER!
    pause
    exit /b 1
)

echo.
echo  Starting organizer for: !FOLDER!
echo  ============================================================
echo.

:: ── Launch Python engine ────────────────────────────────────────
python "%PY_SCRIPT%" "!FOLDER!"

:: ── Keep window open after Python finishes ──────────────────────
echo.
echo  ============================================================
echo   Done. Press any key to close this window.
echo  ============================================================
pause >nul
exit /b 0
