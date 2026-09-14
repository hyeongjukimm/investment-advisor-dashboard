@echo off
setlocal
cd /d "%~dp0"
echo ==========================================================
echo Investment Advisor Tool v4 to v4.1 migration
 echo ==========================================================
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --disable-pip-version-check -q -r requirements.txt
python migrate_from_v4.py
if errorlevel 1 (pause & exit /b 1)
pause
