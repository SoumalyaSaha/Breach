@echo off
REM Breach web UI launcher - starts Streamlit and opens the browser.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
breach web
pause
