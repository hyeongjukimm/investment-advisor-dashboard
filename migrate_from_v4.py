from __future__ import annotations
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent
CANDIDATES = [
    PARENT / "investment_advisor_READY_v4",
    PARENT / "investment_advisor_READY_v4_PORTABLE",
]
SRC = next((p for p in CANDIDATES if p.exists()), None)
if SRC is None:
    raise SystemExit("ERROR: sibling investment_advisor_READY_v4 folder not found.")

(ROOT / "data").mkdir(exist_ok=True)
copy_data = [
    "investment_advisor.sqlite",
    "kosis_cycle_cache.csv",
    "export_flash_cache.csv",
    "company_exposure.csv",
]
for name in copy_data:
    src = SRC / "data" / name
    if src.exists():
        shutil.copy2(src, ROOT / "data" / name)
        print(f"copied data/{name}")

src_secrets = SRC / ".streamlit" / "secrets.toml"
if src_secrets.exists():
    (ROOT / ".streamlit").mkdir(exist_ok=True)
    shutil.copy2(src_secrets, ROOT / ".streamlit" / "secrets.toml")
    print("copied local secrets.toml")

raw = ROOT / "data" / "investment_advisor.sqlite"
if not raw.exists():
    raise SystemExit("ERROR: v4 raw DB was not found. Use MIGRATE_FROM_V3_2 instead.")

print("Rebuilding v4.1 mart with Fundamental Score...")
subprocess.run([sys.executable, str(ROOT / "build_marts.py")], check=True, cwd=ROOT)
print("OK: v4 -> v4.1 migration complete")
