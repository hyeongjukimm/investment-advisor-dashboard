@echo off
setlocal
cd /d "%~dp0"
echo ==========================================================
echo Investment Advisor - Web deployment preparation
echo ==========================================================
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 (echo [ERROR] Python virtual environment failed.& pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (echo [ERROR] Package install failed.& pause & exit /b 1)
if not exist "data\investment_advisor.sqlite" (
  echo [ERROR] data\investment_advisor.sqlite not found.
  pause
  exit /b 1
)
echo [1/3] Building analysis Mart...
python build_marts.py
if errorlevel 1 (echo [ERROR] Mart build failed.& pause & exit /b 1)
echo [2/3] Creating and validating share snapshot...
python -c "from pathlib import Path; from mart_builder import make_share_snapshot; make_share_snapshot(Path('data/investment_mart.sqlite'),Path('data/share_snapshot.sqlite'))"
python validate_snapshot.py data\share_snapshot.sqlite
if errorlevel 1 (echo [ERROR] Snapshot validation failed.& pause & exit /b 1)
echo [3/3] Creating raw-state.zip for GitHub Release...
python -c "from pathlib import Path; import zipfile; names=['investment_advisor.sqlite','kosis_cycle_cache.csv','export_flash_cache.csv']; z=zipfile.ZipFile('raw-state.zip','w',zipfile.ZIP_DEFLATED); [z.write(Path('data')/n,Path('data')/n) for n in names if (Path('data')/n).exists()]; z.close()"
if errorlevel 1 (echo [ERROR] raw-state.zip failed.& pause & exit /b 1)
echo.
echo [OK] data\share_snapshot.sqlite
echo [OK] raw-state.zip
echo Next: follow README_WEB_DEPLOY.md
pause
