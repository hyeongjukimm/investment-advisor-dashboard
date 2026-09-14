from __future__ import annotations

from datetime import datetime
from pathlib import Path
import html as html_lib
import re

import pandas as pd
import requests

CUSTOMS_HOME = "https://www.customs.go.kr/kcs/main.do"


def normalize_flash_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize current and legacy flash-cache columns to canonical names."""
    out = df.copy()
    aliases = {
        "checkpoint_days": "checkpoint_day",
        "yoy_pct": "export_yoy_pct",
    }
    for old, new in aliases.items():
        if new not in out.columns and old in out.columns:
            out[new] = out[old]
    if "export_usd_m" not in out.columns and "export_usd" in out.columns:
        out["export_usd_m"] = pd.to_numeric(out["export_usd"], errors="coerce") / 1_000_000
    required = ["month", "checkpoint_day", "export_usd_m", "import_usd_m",
                "balance_usd_m", "export_yoy_pct", "import_yoy_pct", "source", "status"]
    for col in required:
        if col not in out.columns:
            out[col] = pd.NA
    return out


def _num(s):
    return float(str(s).replace(",", ""))


def parse_customs_homepage_flash(text: str, year: int | None = None) -> dict:
    """Parse the Customs homepage current-period summary.

    The homepage exposes only the current official checkpoint; this parser never
    creates unreported daily observations.
    """
    year = int(year or datetime.now().year)
    # Homepage fetches return HTML; tests and cached sources may already be plain text.
    plain = html_lib.unescape(re.sub(r"<[^>]+>", " ", text))
    compact = re.sub(r"\s+", " ", plain)
    period = re.search(r"당월\s*\(\s*(\d{1,2})\.\s*1\s*[-~∼]\s*\1\.\s*(\d{1,2})\s*\)", compact)
    if not period:
        period = re.search(r"당월\s*\(\s*(\d{1,2})\.\s*1\s*[-~∼]\s*(?:\d{1,2}\.)?\s*(\d{1,2})\s*\)", compact)
    if not period:
        raise ValueError("Could not find current Customs checkpoint period")
    month, day = int(period.group(1)), int(period.group(2))
    after = compact[period.end():]
    m = re.search(r"수출\s*([\d,]+)\s*([△\-+]?\d+(?:\.\d+)?)\s*수입\s*([\d,]+)\s*([△\-+]?\d+(?:\.\d+)?)", after)
    if not m:
        raise ValueError("Could not parse current Customs export/import totals")
    def rate(v):
        v = v.replace("△", "-")
        return float(v)
    export_m, export_yoy, import_m, import_yoy = _num(m.group(1)), rate(m.group(2)), _num(m.group(3)), rate(m.group(4))
    return {
        "month": f"{year:04d}-{month:02d}",
        "checkpoint_day": day,
        "export_usd_m": export_m,
        "import_usd_m": import_m,
        "balance_usd_m": export_m - import_m,
        "export_yoy_pct": export_yoy,
        "import_yoy_pct": import_yoy,
        "source": "관세청 홈페이지",
        "status": "집계중" if day < 28 else "월말 잠정",
    }


def load_flash_snapshots(seed_path: str | Path, cache_path: str | Path | None = None) -> pd.DataFrame:
    frames = []
    for p in [Path(seed_path), Path(cache_path) if cache_path else None]:
        if p and p.exists():
            try:
                frames.append(pd.read_csv(p, dtype={"month":str}))
            except Exception:
                pass
    if not frames:
        return pd.DataFrame(columns=["month","checkpoint_day","export_usd_m","import_usd_m","balance_usd_m","export_yoy_pct","import_yoy_pct","source","status"])
    out = normalize_flash_schema(pd.concat(frames, ignore_index=True, sort=False))
    out["checkpoint_day"] = pd.to_numeric(out["checkpoint_day"], errors="coerce")
    for c in ["export_usd_m","import_usd_m","balance_usd_m","export_yoy_pct","import_yoy_pct"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out.sort_values(["month","checkpoint_day"]).drop_duplicates(["month","checkpoint_day"], keep="last").reset_index(drop=True)


def refresh_flash_cache(cache_path: str | Path, timeout: int = 20, verify_ssl: bool = True) -> dict:
    """Best-effort refresh of the current official homepage checkpoint."""
    cache_path = Path(cache_path)
    try:
        r = requests.get(CUSTOMS_HOME, timeout=timeout, verify=verify_ssl, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        row = parse_customs_homepage_flash(r.text, year=datetime.now().year)
        row["fetched_at"] = datetime.now().isoformat(timespec="seconds")
        existing = pd.read_csv(cache_path) if cache_path.exists() else pd.DataFrame()
        out = pd.concat([existing, pd.DataFrame([row])], ignore_index=True, sort=False)
        out = out.drop_duplicates(["month","checkpoint_day"], keep="last")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(cache_path, index=False)
        return {"ok": True, "row": row}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def flash_comparison_frame(df: pd.DataFrame, month: str, checkpoint_day: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    target = pd.Period(month, freq="M")
    candidates = [(target, "현재"), (target - 12, "전년동기"), (target - 1, "전월동일구간")]
    rows = []
    for period, label in candidates:
        part = df[(df["month"].astype(str) == str(period)) & (pd.to_numeric(df["checkpoint_day"], errors="coerce") == int(checkpoint_day))]
        if not part.empty:
            r = part.iloc[-1].to_dict(); r["comparison"] = label; rows.append(r)
    # Five-year same-month average is shown only when at least three historical observations exist.
    hist = df[(pd.to_numeric(df["checkpoint_day"], errors="coerce") == int(checkpoint_day))].copy()
    hist["period"] = hist["month"].map(lambda x: pd.Period(str(x), freq="M"))
    hist = hist[(hist["period"].dt.month == target.month) & (hist["period"] < target) & (hist["period"] >= target - 60)]
    if len(hist) >= 3:
        rows.append({
            "month": "최근5년 평균", "checkpoint_day": checkpoint_day,
            "export_usd_m": hist["export_usd_m"].mean(), "import_usd_m": hist["import_usd_m"].mean(),
            "balance_usd_m": hist.get("balance_usd_m", pd.Series(dtype=float)).mean(),
            "export_yoy_pct": hist.get("export_yoy_pct", pd.Series(dtype=float)).mean(),
            "import_yoy_pct": hist.get("import_yoy_pct", pd.Series(dtype=float)).mean(),
            "comparison": "최근5년동월평균", "source":"관세청 과거 잠정치", "status":"비교",
        })
    return pd.DataFrame(rows)
