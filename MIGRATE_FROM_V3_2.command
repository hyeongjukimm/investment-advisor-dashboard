#!/bin/bash
set -e
cd "$(dirname "$0")"
SRC="../investment_advisor_READY_v3.2"
echo "=========================================================="
echo "v4.1 migration from v3.2"
echo "=========================================================="
if [ ! -d "$SRC" ]; then
  echo "[ERROR] sibling folder not found: $SRC"
  echo "Put investment_advisor_READY_v3.2 and v4.1 side-by-side on Desktop."
  exit 1
fi
if [ ! -d ".venv" ]; then python3 -m venv .venv; fi
source .venv/bin/activate
if [ ! -f ".venv/.requirements_v4" ] || [ requirements.txt -nt ".venv/.requirements_v4" ]; then
  echo "Installing v4.1 requirements..."
  python3 -m pip install --disable-pip-version-check -q -r requirements.txt
  touch .venv/.requirements_v4
fi
mkdir -p data .streamlit
[ -f "$SRC/data/investment_advisor.sqlite" ] && cp "$SRC/data/investment_advisor.sqlite" data/
[ -f "$SRC/data/kosis_cycle_cache.csv" ] && cp "$SRC/data/kosis_cycle_cache.csv" data/
[ -f "$SRC/data/export_flash_cache.csv" ] && cp "$SRC/data/export_flash_cache.csv" data/
[ -f "$SRC/.streamlit/secrets.toml" ] && cp "$SRC/.streamlit/secrets.toml" .streamlit/secrets.toml

echo "Copied local DB/cache/secrets when present."
python3 build_marts.py
echo "Migration + v4.1 mart build complete."
