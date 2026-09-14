@echo off
setlocal
cd /d "%~dp0"
set "SRC=..\investment_advisor_READY_v3.2"
if not exist "%SRC%" (
  echo [ERROR] sibling v3.2 folder not found: %SRC%
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
call ".venv\Scripts\activate.bat"
if not exist ".venv\.requirements_v4" (
  echo Installing v4.1 requirements...
  python -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 (echo [ERROR] Package install failed.& pause & exit /b 1)
  type nul > ".venv\.requirements_v4"
)
if not exist data mkdir data
if not exist .streamlit mkdir .streamlit
if exist "%SRC%\data\investment_advisor.sqlite" copy /Y "%SRC%\data\investment_advisor.sqlite" "data\" >nul
if exist "%SRC%\data\kosis_cycle_cache.csv" copy /Y "%SRC%\data\kosis_cycle_cache.csv" "data\" >nul
if exist "%SRC%\data\export_flash_cache.csv" copy /Y "%SRC%\data\export_flash_cache.csv" "data\" >nul
if exist "%SRC%\.streamlit\secrets.toml" copy /Y "%SRC%\.streamlit\secrets.toml" ".streamlit\secrets.toml" >nul
python build_marts.py
pause
