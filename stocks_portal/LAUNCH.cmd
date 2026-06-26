@echo off
REM ===========================================================
REM Simplest possible launcher. .cmd extension to bypass any
REM .bat-specific blockers. Double-click this file.
REM ===========================================================
title EquityTerm
cd /d "%~dp0"
echo.
echo ============================================================
echo  Starting EquityTerm...
echo  When the browser opens, leave this window OPEN.
echo  To stop: press Ctrl+C in this window.
echo ============================================================
echo.

python -m streamlit run app.py

echo.
echo ============================================================
echo  Streamlit exited. Press any key to close this window.
echo ============================================================
pause >nul
