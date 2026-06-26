@echo off
REM ============================================================
REM EquityTerm - Dependency installer (double-click)
REM Runs the pip install ONCE. After this, use run.bat normally.
REM ============================================================
setlocal
cd /d "%~dp0"
title EquityTerm - Installing dependencies

echo ============================================================
echo  EquityTerm - Installing dependencies
echo  This window will close itself when done. ~60 seconds.
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo Install from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [1/3] Upgrading pip...
python -m pip install --upgrade pip
echo.

echo [2/3] Installing required packages...
python -m pip install streamlit yfinance pandas numpy plotly requests feedparser python-dateutil python-dotenv lxml beautifulsoup4
if errorlevel 1 (
    echo.
    echo [ERROR] Install failed. Most likely cause: lxml needs build tools.
    echo Try this fallback in CMD manually:
    echo   pip install streamlit yfinance pandas numpy plotly requests feedparser python-dotenv
    echo (skips lxml - sector heatmap and Dataroma scraping won't work but rest will)
    echo.
    pause
    exit /b 1
)

echo.
echo [3/3] Marking install complete...
echo. > .deps_installed
echo.
echo ============================================================
echo  [OK] All dependencies installed successfully.
echo
echo  Now double-click run.bat to launch EquityTerm.
echo ============================================================
echo.
pause
