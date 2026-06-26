# PowerShell launcher — alternative if .bat / .cmd are blocked.
# To run: right-click this file → "Run with PowerShell"
# Or in PowerShell: cd to this folder, then .\launch.ps1

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "============================================================"
Write-Host " Starting EquityTerm..."
Write-Host " When the browser opens, leave this window OPEN."
Write-Host " To stop: press Ctrl+C in this window."
Write-Host "============================================================"
Write-Host ""

python -m streamlit run app.py

Write-Host ""
Write-Host "============================================================"
Write-Host " Streamlit exited. Press Enter to close."
Write-Host "============================================================"
Read-Host
