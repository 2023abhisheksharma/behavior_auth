@echo off
cd /d "%~dp0"
call python_engine\venv\Scripts\activate.bat
python python_engine\desktop_app.py

