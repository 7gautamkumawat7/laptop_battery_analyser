@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo         VoltPulse Desktop Application Build System
echo ========================================================
echo.

:: 1. Clean previous build artifacts
echo [1/3] Cleaning previous build artifacts...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
echo Clean completed successfully.
echo.

:: 2. Identify Python / PyInstaller executable
echo [2/3] Compiling VoltPulse with PyInstaller...

set "PY_CMD=pyinstaller"
if exist "D:\anaconda\Scripts\pyinstaller.exe" (
    set "PY_CMD=D:\anaconda\Scripts\pyinstaller.exe"
)

echo Using PyInstaller: !PY_CMD!
echo Compiling VoltPulse standalone windowed executable...
echo.

!PY_CMD! --noconfirm --clean VoltPulse.spec

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================
    echo [ERROR] Build failed with exit code %ERRORLEVEL%!
    echo Check the error logs above for details.
    echo ========================================================
    if not "%1"=="--no-pause" pause
    exit /b %ERRORLEVEL%
)

:: 3. Build verification
echo.
echo [3/3] Verifying generated executable...
if exist "dist\VoltPulse.exe" (
    echo.
    echo ========================================================
    echo [SUCCESS] VoltPulse Desktop Executable Built Successfully!
    echo Binary Location: dist\VoltPulse.exe
    echo ========================================================
    echo.
) else (
    echo.
    echo [WARNING] dist\VoltPulse.exe was not found. Please review the build log.
    echo.
)

if not "%1"=="--no-pause" pause
