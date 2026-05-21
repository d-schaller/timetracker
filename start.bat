@echo off
REM Startet den Time Tracker
REM Benoetigt Python 3.8+ (https://www.python.org/downloads/)

where python >nul 2>&1
if errorlevel 1 (
    echo Python nicht gefunden. Bitte von https://www.python.org/downloads/ installieren.
    pause
    exit /b 1
)

python "%~dp0timetracker.py"
if errorlevel 1 pause
