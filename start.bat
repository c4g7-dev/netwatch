@echo off
REM NetWatch Launcher Script for Windows

cd /d "%~dp0"

if not exist ".venv" (
    echo Error: Virtual environment not found. Run 'python -m venv .venv' first.
    exit /b 1
)

call .venv\Scripts\activate.bat
python main.py %*
