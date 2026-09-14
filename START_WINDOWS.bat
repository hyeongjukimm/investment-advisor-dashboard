@echo off
setlocal
cd /d "%~dp0"
echo ==========================================================
echo Investment Advisor Tool v4.1 - Windows
echo ==========================================================
python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.11+ and retry.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
if not exist ".venv\.requirements_v4" (
  echo [2/3] Installing requirements...
  python -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 (echo [ERROR] Package install failed.& pause & exit /b 1)
  type nul > ".venv\.requirements_v4"
) else (
  echo [2/3] Requirements already installed.
)
echo [3/3] Starting Streamlit...
echo Opening http://127.0.0.1:8501 in your browser...
start "" http://127.0.0.1:8501
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
pause
