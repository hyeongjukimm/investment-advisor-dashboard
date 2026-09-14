from __future__ import annotations

import numpy as np
import pandas as pd


def _monthly_entity(df: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["date", entity_col, "export_usd"])
    x = df[["date", entity_col, "export_usd"]].copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce")
    x["export_usd"] = pd.to_numeric(x["export_usd"], errors="coerce").fillna(0.0)
    x = x.dropna(subset=["date", entity_col])
    return x.groupby(["date", entity_col], as_index=False, dropna=False)["export_usd"].sum()


def prepare_chartbook_series(df: pd.DataFrame, entity_col: str, entity_value: str) -> pd.DataFrame:
    base = _monthly_entity(df, entity_col)
    x = base[base[entity_col].astype(str) == str(entity_value)].sort_values("date").copy()
    if x.empty:
        return x
    x["mom_pct"] = x["export_usd"].pct_change(1, fill_method=None) * 100
    x["yoy_pct"] = x["export_usd"].pct_change(12, fill_method=None) * 100
    x["yoy_3m_avg"] = x["yoy_pct"].rolling(3, min_periods=1).mean()
    x["year"] = x["date"].dt.year
    x["month_num"] = x["date"].dt.month
    x["ytd_usd"] = x.groupby("year")["export_usd"].cumsum()
    prev = x[["year", "month_num", "ytd_usd"]].copy()
    prev["year"] = prev["year"] + 1
    prev = prev.rename(columns={"ytd_usd": "prior_year_ytd_usd"})
    x = x.merge(prev, on=["year", "month_num"], how="left")
    x["ytd_yoy_pct"] = (x["ytd_usd"] / x["prior_year_ytd_usd"] - 1) * 100
    return x


def _period_endpoint_stats(part: pd.DataFrame, entity_col: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for entity, g in part.groupby(entity_col, dropna=False):
        g = g.sort_values("date")
        if g.empty:
            continue
        n = min(3, len(g))
        start_run = g.head(n)["export_usd"].mean()
        end_run = g.tail(n)["export_usd"].mean()
        growth = (end_run / start_run - 1) * 100 if start_run else np.nan
        abs_inc = end_run - start_run
        yoy = g["yoy_pct"] if "yoy_pct" in g.columns else (g["export_usd"].pct_change(12, fill_method=None) * 100)
        rows.append({
            "entity": entity,
            "period_start": start,
            "period_end": end,
            "start_run_rate_usd": start_run,
            "end_run_rate_usd": end_run,
            "growth_pct": growth,
            "absolute_increase_usd": abs_inc,
            "period_export_usd": g["export_usd"].sum(),
            "avg_yoy_pct": yoy.mean() if not yoy.empty else np.nan,
            "latest_yoy_pct": yoy.iloc[-1] if not yoy.empty else np.nan,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    total_inc = out["absolute_increase_usd"].sum()
    out["contribution_pct"] = out["absolute_increase_usd"] / total_inc * 100 if total_inc else 0.0
    return out


def _previous_period_stats(base: pd.DataFrame, entity_col: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    prev_end = start - pd.DateOffset(months=1)
    prev_start = prev_end - pd.DateOffset(months=months - 1)
    cur = base[(base["date"] >= start) & (base["date"] <= end)].groupby(entity_col, as_index=False)["export_usd"].sum().rename(columns={"export_usd":"current_usd"})
    prev = base[(base["date"] >= prev_start) & (base["date"] <= prev_end)].groupby(entity_col, as_index=False)["export_usd"].sum().rename(columns={"export_usd":"previous_usd"})
    out = cur.merge(prev, on=entity_col, how="left").fillna({"previous_usd":0.0})
    out["entity"] = out[entity_col]
    out["growth_pct"] = np.where(out["previous_usd"] > 0, (out["current_usd"] / out["previous_usd"] - 1) * 100, np.nan)
    out["absolute_increase_usd"] = out["current_usd"] - out["previous_usd"]
    total_inc = out["absolute_increase_usd"].sum()
    out["contribution_pct"] = out["absolute_increase_usd"] / total_inc * 100 if total_inc else 0.0
    out["period_export_usd"] = out["current_usd"]
    out["start_run_rate_usd"] = np.nan
    out["end_run_rate_usd"] = np.nan
    out["avg_yoy_pct"] = np.nan
    out["latest_yoy_pct"] = np.nan
    return out.drop(columns=[entity_col])


def growth_leaders(
    df: pd.DataFrame,
    entity_col: str,
    start,
    end,
    min_base_usd: float = 0.0,
    mode: str = "endpoint",
) -> pd.DataFrame:
    base = _monthly_entity(df, entity_col)
    base = base.sort_values([entity_col, "date"]).reset_index(drop=True)
    base["yoy_pct"] = base.groupby(entity_col, dropna=False)["export_usd"].pct_change(12, fill_method=None) * 100
    start = pd.Timestamp(start).to_period("M").to_timestamp()
    end = pd.Timestamp(end).to_period("M").to_timestamp()
    if start > end:
        start, end = end, start
    part = base[(base["date"] >= start) & (base["date"] <= end)].copy()
    if mode == "previous_period":
        out = _previous_period_stats(base, entity_col, start, end)
        yoy_part = base[(base["date"] >= start) & (base["date"] <= end)].copy()
        yoy_stats = yoy_part.groupby(entity_col, dropna=False)["yoy_pct"].agg([("avg_yoy_pct", "mean"), ("latest_yoy_pct", "last")]).reset_index().rename(columns={entity_col:"entity"})
        if not out.empty:
            out = out.drop(columns=["avg_yoy_pct","latest_yoy_pct"], errors="ignore").merge(yoy_stats, on="entity", how="left")
        base_metric = out.get("previous_usd", pd.Series(dtype=float))
    else:
        out = _period_endpoint_stats(part, entity_col, start, end)
        base_metric = out.get("start_run_rate_usd", pd.Series(dtype=float))
    if out.empty:
        return out
    out = out[pd.to_numeric(base_metric, errors="coerce").fillna(0) >= float(min_base_usd)].copy()
    return out.sort_values(["growth_pct", "absolute_increase_usd"], ascending=[False, False]).reset_index(drop=True)


def cycle_polynomial_curve(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    order: int = 3,
    points: int = 100,
) -> tuple[pd.DataFrame, pd.Series]:
    order = int(order)
    if order not in {2, 3, 4}:
        raise ValueError("order must be 2, 3, or 4")
    x = df.copy()
    x[x_col] = pd.to_numeric(x[x_col], errors="coerce")
    x[y_col] = pd.to_numeric(x[y_col], errors="coerce")
    x = x.dropna(subset=[x_col, y_col]).copy()
    if "date" in x.columns:
        x = x.sort_values("date")
    if len(x) < order + 1 or x[x_col].nunique() < order + 1:
        return pd.DataFrame(columns=["x_fit", "y_fit"]), (x.iloc[-1] if not x.empty else pd.Series(dtype=float))
    coeff = np.polyfit(x[x_col].to_numpy(), x[y_col].to_numpy(), order)
    fit_x = np.linspace(x[x_col].min(), x[x_col].max(), int(points))
    fit_y = np.polyval(coeff, fit_x)
    return pd.DataFrame({"x_fit": fit_x, "y_fit": fit_y}), x.iloc[-1]


def mapping_waterfall(coverage_row) -> pd.DataFrame:
    row = dict(coverage_row)
    return pd.DataFrame({
        "step": ["HS10 전체", "Top20 매핑", "미매핑 Gap"],
        "value_usd": [float(row.get("total_export_usd", 0) or 0), float(row.get("mapped_export_usd", 0) or 0), float(row.get("unmapped_export_usd", 0) or 0)],
    })
