#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "=========================================================="
echo "Investment Advisor Tool v4.1 - macOS"
echo "=========================================================="
if [ ! -d ".venv" ]; then
  echo "[1/3] Creating virtual environment..."
  python3 -m venv .venv
fi
source .venv/bin/activate
if [ ! -f ".venv/.requirements_v4" ] || [ requirements.txt -nt ".venv/.requirements_v4" ]; then
  echo "[2/3] Installing requirements (first run / changed requirements)..."
  python3 -m pip install --disable-pip-version-check -q -r requirements.txt
  touch .venv/.requirements_v4
else
  echo "[2/3] Requirements already installed."
fi
echo "[3/3] Starting Streamlit..."
python3 -m streamlit run app.py
