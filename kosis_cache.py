from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


def write_kosis_cache(df: pd.DataFrame, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    if "PRD_DE" in out.columns:
        out["PRD_DE"] = out["PRD_DE"].astype(str)
    out.to_csv(p, index=False)


def read_kosis_cache(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    try:
        out = pd.read_csv(p, dtype={"PRD_DE": str, "IND_CODE": str})
    except Exception:
        return pd.DataFrame()
    if "PRD_DE" in out.columns:
        out["PRD_DE"] = out["PRD_DE"].astype(str).str.replace(r"\.0$", "", regex=True)
    return out


def cache_status(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"exists": False, "rows": 0, "latest_period": None, "updated_at": None}
    df = read_kosis_cache(p)
    latest = None
    if not df.empty and "PRD_DE" in df.columns:
        vals = df["PRD_DE"].dropna().astype(str)
        latest = vals.max() if not vals.empty else None
    return {
        "exists": True,
        "rows": int(len(df)),
        "latest_period": latest,
        "updated_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
    }
