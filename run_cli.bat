@echo off
REM Breach CLI launcher - double-click, or run from a terminal.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
breach chat
pause
