@echo off
cd /d "%~dp0"
py -3 -m venv .venv || (echo Python not found. Install it from python.org and tick "Add to PATH". & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -c "import tkinter, qrcode, PIL, reportlab, openpyxl; print('OK - all dependencies installed')"
pause
