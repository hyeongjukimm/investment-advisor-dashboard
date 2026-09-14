#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "=========================================================="
echo "Investment Advisor Tool v4 -> v4.1 migration"
echo "=========================================================="
if [ ! -d ".venv" ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python3 -m pip install --disable-pip-version-check -q -r requirements.txt
python3 migrate_from_v4.py
