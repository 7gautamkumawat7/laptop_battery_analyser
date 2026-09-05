@echo off
title VoltPulse - Battery Health & Analytics Dashboard
echo ========================================================
echo   VoltPulse - Battery Health & Diagnostics Web Dashboard
echo ========================================================
echo.
echo Starting Flask web server...

if exist "d:\anaconda\python.exe" (
    "d:\anaconda\python.exe" app.py
) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" app.py
) else (
    python app.py
)

pause
