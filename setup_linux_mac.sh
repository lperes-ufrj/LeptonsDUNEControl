#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
# On Ubuntu/WSL Tkinter is a separate package:  sudo apt install python3-tk python3-venv
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -c "import tkinter, qrcode, PIL, reportlab, openpyxl; print('OK - all dependencies installed')"
