@echo off
REM Activate Python virtual environment in .venv folder
REM Usage: activate_venv.bat

REM Get the directory where this batch file is located
set SCRIPT_DIR=%~dp0

REM Check if .venv folder exists
if not exist "%SCRIPT_DIR%.venv" (
    echo Error: .venv folder not found in %SCRIPT_DIR%
    echo Create virtual environment with: python -m venv .venv
    pause
    exit /b 1
)

REM Check if activation script exists
if not exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" (
    echo Error: Virtual environment activation script not found
    echo Expected: %SCRIPT_DIR%.venv\Scripts\activate.bat
    pause
    exit /b 1
)

REM Activate the virtual environment
echo Activating virtual environment...
call "%SCRIPT_DIR%.venv\Scripts\activate.bat"

REM Check if activation was successful
if errorlevel 1 (
    echo Error: Failed to activate virtual environment
    pause
    exit /b 1
)

echo Virtual environment activated successfully!
echo Python location: %VIRTUAL_ENV%\Scripts\python.exe
echo To deactivate, type: deactivate

REM Keep command prompt open
cmd /k