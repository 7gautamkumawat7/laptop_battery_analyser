@echo off
title VoltPulse - Battery Health & Analytics Dashboard
echo ========================================================
echo   VoltPulse - Battery Health & Diagnostics Web Dashboard
echo ========================================================
echo.
echo Starting VoltPulse Desktop Application...

if exist "d:\anaconda\python.exe" (
    "d:\anaconda\python.exe" main.py
) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" main.py
) else (
    python main.py
)

pause
