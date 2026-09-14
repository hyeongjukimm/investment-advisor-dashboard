@echo off
setlocal
cd /d "%~dp0"
echo ==========================================================
echo Investment Advisor Tool v4.1 - Company ZIP
 echo ==========================================================
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --disable-pip-version-check -q -r requirements.txt
python make_portable.py
if errorlevel 1 (pause & exit /b 1)
pause
