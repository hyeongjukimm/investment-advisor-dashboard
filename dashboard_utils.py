from __future__ import annotations

import math
from typing import Any

import pandas as pd

USD_PER_100M = 100_000_000.0


def _month_start(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        raise ValueError("date cannot be NaT")
    return ts.to_period("M").to_timestamp()


def normalize_month_range(start: Any, end: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Normalize two date-like values to ordered month-start timestamps."""
    s = _month_start(start)
    e = _month_start(end)
    return (s, e) if s <= e else (e, s)


def quick_month_range(latest: Any, preset: str, available_start: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return an inclusive monthly range ending at ``latest`` for common presets."""
    end = _month_start(latest)
    floor = _month_start(available_start)
    if preset == "전체":
        return min(floor, end), end
    months_by_preset = {"1Y": 12, "3Y": 36, "5Y": 60, "10Y": 120}
    if preset not in months_by_preset:
        raise ValueError(f"unsupported preset: {preset}")
    months = months_by_preset[preset]
    start = end - pd.DateOffset(months=months - 1)
    return max(start, floor), end


def filter_month_range(df: pd.DataFrame, start: Any, end: Any, date_col: str = "date") -> pd.DataFrame:
    """Filter a frame to an inclusive month range without mutating the source."""
    if df.empty or date_col not in df.columns:
        return df.copy()
    s, e = normalize_month_range(start, end)
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    return out[(out[date_col] >= s) & (out[date_col] <= e)].copy()


def industry_period_summary(signal: pd.DataFrame) -> pd.DataFrame:
    """Attach selected-period average and change to each industry's latest row."""
    if signal.empty:
        return signal.copy()
    work = signal.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["fundamental_score"] = pd.to_numeric(work["fundamental_score"], errors="coerce")
    work = work.dropna(subset=["date", "item20"]).sort_values(["item20", "date"])
    latest = work.groupby("item20", as_index=False).tail(1).copy()
    stats = work.groupby("item20", as_index=False).agg(
        period_avg_score=("fundamental_score", "mean"),
        period_first_score=("fundamental_score", "first"),
    )
    out = latest.merge(stats, on="item20", how="left")
    out["period_change_score"] = out["fundamental_score"] - out["period_first_score"]
    return out


def usd_to_100m(value: Any):
    """Convert raw USD to 100-million-USD units (억달러)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return float(value) / USD_PER_100M


def format_100m_usd(value: Any, decimals: int = 1) -> str:
    converted = usd_to_100m(value)
    if converted is None or not math.isfinite(converted):
        return "-"
    return f"{converted:,.{int(decimals)}f}억달러"
