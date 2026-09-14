#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ -x ".venv/bin/python" ]; then PY=.venv/bin/python; else PY=python3; fi
$PY make_portable.py
