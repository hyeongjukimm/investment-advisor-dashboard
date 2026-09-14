#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ -x ".venv/bin/python" ]; then PY=.venv/bin/python; else PY=python3; fi
$PY build_marts.py
