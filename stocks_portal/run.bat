@echo off
REM ============================================================
REM EquityTerm - One-click launcher for Windows
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo  EquityTerm - Position Trading Decision Terminal
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo Install from https://www.python.org/downloads/  (tick "Add to PATH").
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] Python !PYVER! detected.
echo.

if not exist ".deps_installed" (
    echo [INFO] First-time setup. Installing dependencies (~60s)...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 ( pause & exit /b 1 )
    echo. > .deps_installed
    echo [OK] Dependencies installed.
    echo.
)

echo [INFO] Launching EquityTerm at http://localhost:8502
echo       Press Ctrl+C in this window to stop.
echo.
streamlit run app.py
pause
