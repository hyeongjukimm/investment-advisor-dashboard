from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sqlite3

import numpy as np
import pandas as pd


REQUIRED_TAXONOMY = [
    "20대품목", "리서치중분류", "대표품목명", "MTI6", "HSK10", "HS6", "HS4", "HSK 품목명"
]


def _clean(series: pd.Series, width: int | None = None) -> pd.Series:
    out = series.fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    if width:
        out = out.str.zfill(width)
    return out


def load_taxonomy(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_csv(path, dtype=str).fillna("")
    missing = [c for c in REQUIRED_TAXONOMY if c not in df.columns]
    if missing:
        raise ValueError(f"Taxonomy missing columns: {missing}")
    if df["HSK10"].astype(str).nunique() != len(df):
        raise ValueError("Taxonomy HSK10 must be unique")

    out = pd.DataFrame({
        "hsk10": _clean(df["HSK10"], 10),
        "item20": _clean(df["20대품목"]),
        "middle_category": _clean(df["리서치중분류"]),
        "product": _clean(df["대표품목명"]),
        "representative_id": _clean(df.get("대표품목ID", pd.Series("", index=df.index))),
        "research_large": _clean(df.get("리서치대분류", pd.Series("", index=df.index))),
        "research_small": _clean(df.get("리서치소분류", pd.Series("", index=df.index))),
        "research_detail": _clean(df.get("리서치세분류", pd.Series("", index=df.index))),
        "mti6": _clean(df["MTI6"]),
        "hs6": _clean(df["HS6"], 6),
        "hs4": _clean(df["HS4"], 4),
        "official_name": _clean(df["HSK 품목명"]),
        "drilldown_name": _clean(df.get("드릴다운명", pd.Series("", index=df.index))),
        "drilldown_id": _clean(df.get("드릴다운ID", pd.Series("", index=df.index))),
        "classification_status": _clean(df.get("분류상태", pd.Series("", index=df.index))),
        "classification_note": _clean(df.get("분류메모", pd.Series("", index=df.index))),
    })
    out["middle_category"] = out["middle_category"].where(out["middle_category"] != "", "기타")
    out["product"] = out["product"].where(out["product"] != "", out["middle_category"])
    out["display_name"] = out["drilldown_name"].where(out["drilldown_name"] != "", out["product"])
    out["display_name"] = out["display_name"].where(out["display_name"] != "", out["official_name"])
    return out.drop_duplicates("hsk10").reset_index(drop=True)


def _trade_metrics(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    x = df.copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce")
    numeric = ["export_usd", "import_usd", "export_weight", "import_weight", "balance_usd"]
    for c in numeric:
        if c not in x.columns:
            x[c] = 0.0
        x[c] = pd.to_numeric(x[c], errors="coerce").fillna(0.0)
    calendar = pd.DataFrame({"date": pd.date_range(x["date"].min(), x["date"].max(), freq="MS")})
    if group_cols:
        groups = x[group_cols].drop_duplicates()
        grid = groups.merge(calendar, how="cross")
        x = grid.merge(x, on=group_cols + ["date"], how="left")
    else:
        x = calendar.merge(x, on="date", how="left")
    x = x.sort_values(group_cols + ["date"]).reset_index(drop=True)
    if group_cols:
        g = x.groupby(group_cols, dropna=False)
        x["mom_pct"] = g["export_usd"].pct_change(1, fill_method=None) * 100
        x["yoy_pct"] = g["export_usd"].pct_change(12, fill_method=None) * 100
        x["year"] = x["date"].dt.year
        x["ytd_usd"] = x.groupby(group_cols + ["year"], dropna=False)["export_usd"].cumsum()
    else:
        x["mom_pct"] = x["export_usd"].pct_change(1, fill_method=None) * 100
        x["yoy_pct"] = x["export_usd"].pct_change(12, fill_method=None) * 100
        x["year"] = x["date"].dt.year
        x["ytd_usd"] = x.groupby("year")["export_usd"].cumsum()
    x[["mom_pct", "yoy_pct"]] = x[["mom_pct", "yoy_pct"]].replace([np.inf, -np.inf], np.nan)
    x["unit_price_usd_per_kg"] = x["export_usd"].div(x["export_weight"].replace(0, np.nan))
    return x


def _sql_aggregate(raw_db: Path, taxonomy: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    # Store the compact dimension in the source DB so SQLite can do the heavy join/grouping
    # without materialising millions of raw rows in Python memory.
    select_dim = {
        "item20": "t.item20",
        "middle_category": "t.middle_category",
        "product": "t.product",
    }
    dim_select = ", ".join(select_dim[c] for c in group_cols)
    dim_group = dim_select
    with sqlite3.connect(raw_db) as con:
        taxonomy.to_sql("dim_product_taxonomy_v4", con, if_exists="replace", index=False)
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tax_v4_hsk10 ON dim_product_taxonomy_v4(hsk10)")
        prefix = (dim_select + ", ") if dim_select else ""
        sql = f"""
            SELECT r.date, {prefix}
                   SUM(COALESCE(r.export_usd,0)) AS export_usd,
                   SUM(COALESCE(r.import_usd,0)) AS import_usd,
                   SUM(COALESCE(r.export_weight,0)) AS export_weight,
                   SUM(COALESCE(r.import_weight,0)) AS import_weight,
                   SUM(COALESCE(r.balance_usd,0)) AS balance_usd
            FROM raw_item r
            JOIN dim_product_taxonomy_v4 t ON r.hsk10=t.hsk10
            GROUP BY r.date{',' if dim_group else ''} {dim_group}
            ORDER BY r.date{',' if dim_group else ''} {dim_group}
        """
        out = pd.read_sql_query(sql, con)
    return _trade_metrics(out, group_cols)



def _rollup_trade(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    base_cols = ["export_usd", "import_usd", "export_weight", "import_weight", "balance_usd"]
    grouped = (
        df.groupby(["date"] + group_cols, as_index=False, dropna=False)[base_cols]
        .sum(min_count=1)
    )
    return _trade_metrics(grouped, group_cols)

def _total_and_coverage(raw_db: Path) -> pd.DataFrame:
    with sqlite3.connect(raw_db) as con:
        df = pd.read_sql_query(
            """
            SELECT r.date,
                   SUM(COALESCE(r.export_usd,0)) AS total_export_usd,
                   SUM(CASE WHEN t.hsk10 IS NOT NULL THEN COALESCE(r.export_usd,0) ELSE 0 END) AS mapped_export_usd,
                   SUM(CASE WHEN t.hsk10 IS NULL THEN COALESCE(r.export_usd,0) ELSE 0 END) AS unmapped_export_usd
            FROM raw_item r
            LEFT JOIN dim_product_taxonomy_v4 t ON r.hsk10=t.hsk10
            GROUP BY r.date ORDER BY r.date
            """,
            con,
        )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["mapped_value_pct"] = df["mapped_export_usd"].div(df["total_export_usd"].replace(0, np.nan)) * 100
    df["total_yoy_pct"] = df["total_export_usd"].pct_change(12, fill_method=None) * 100
    return df


def _product_country(raw_db: Path) -> pd.DataFrame:
    with sqlite3.connect(raw_db) as con:
        exists = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_item_country'").fetchone()
        if not exists:
            return pd.DataFrame()
        out = pd.read_sql_query(
            """
            SELECT r.date, r.country_code, t.item20, t.middle_category, t.product,
                   SUM(COALESCE(r.export_usd,0)) AS export_usd,
                   SUM(COALESCE(r.import_usd,0)) AS import_usd,
                   SUM(COALESCE(r.export_weight,0)) AS export_weight,
                   SUM(COALESCE(r.import_weight,0)) AS import_weight,
                   SUM(COALESCE(r.balance_usd,0)) AS balance_usd
            FROM raw_item_country r
            JOIN dim_product_taxonomy_v4 t ON r.hsk10=t.hsk10
            GROUP BY r.date, r.country_code, t.item20, t.middle_category, t.product
            ORDER BY r.date, r.country_code, t.item20, t.middle_category, t.product
            """,
            con,
        )
    return _trade_metrics(out, ["country_code", "item20", "middle_category", "product"])


def _lifecycle(shipment, inventory) -> str:
    if pd.isna(shipment) or pd.isna(inventory):
        return "미편제"
    spread = shipment - inventory
    deadband = 0.8
    if spread >= -deadband:
        return "회복기" if inventory <= deadband else "활황기"
    return "후퇴기" if inventory >= -deadband else "침체기"


def build_kosis_cycle(kosis_cache_path: str | Path) -> pd.DataFrame:
    empty = pd.DataFrame(columns=[
        "date", "ksic_code", "production_index", "shipment_index", "inventory_index",
        "production_yoy", "shipment_yoy", "inventory_yoy", "inventory_cycle", "stage"
    ])
    p = Path(kosis_cache_path)
    if not p.exists():
        return empty
    raw = pd.read_csv(p)
    needed = {"PRD_DE", "IND_CODE", "ITM_NM", "DT_val"}
    if not needed.issubset(raw.columns):
        return empty
    raw["PRD_DE"] = raw["PRD_DE"].astype(str).str.replace(r"\.0$", "", regex=True)
    raw["DT_val"] = pd.to_numeric(raw["DT_val"], errors="coerce")
    frames = []
    for code, part in raw.groupby(raw["IND_CODE"].astype(str)):
        piv = part.pivot_table(index="PRD_DE", columns="ITM_NM", values="DT_val", aggfunc="first").sort_index()
        piv = piv.rename(columns={
            "생산지수(계절조정)": "production_index",
            "생산자제품 출하지수(계절조정)": "shipment_index",
            "생산자제품 재고지수(계절조정)": "inventory_index",
        })
        for src, dst in [("production_index", "production_yoy"), ("shipment_index", "shipment_yoy"), ("inventory_index", "inventory_yoy")]:
            if src in piv.columns:
                yoy = piv[src].pct_change(12, fill_method=None) * 100
                piv[dst] = yoy.rolling(3, min_periods=1).mean()
            else:
                piv[dst] = np.nan
        piv["inventory_cycle"] = piv["shipment_yoy"] - piv["inventory_yoy"]
        piv["date"] = pd.to_datetime(piv.index.astype(str), format="%Y%m", errors="coerce")
        piv["ksic_code"] = str(code)
        keep = ["date", "ksic_code", "production_index", "shipment_index", "inventory_index", "production_yoy", "shipment_yoy", "inventory_yoy", "inventory_cycle"]
        for c in keep:
            if c not in piv.columns:
                piv[c] = np.nan
        frames.append(piv[keep].reset_index(drop=True))
    if not frames:
        return empty
    out = pd.concat(frames, ignore_index=True)
    out["stage"] = [_lifecycle(s, i) for s, i in zip(out["shipment_yoy"], out["inventory_yoy"])]
    return out.dropna(subset=["date"]).sort_values(["date", "ksic_code"])



def _absolute_rank_score(values: pd.Series, *, scale: float, group: pd.Series) -> pd.Series:
    """Blend absolute improvement with cross-sectional rank into a 0-100 score.

    The absolute leg prevents a weak industry from scoring highly merely because peers are worse.
    The rank leg keeps the scanner useful for relative Top-down selection.
    """
    v = pd.to_numeric(values, errors="coerce")
    absolute = (50.0 + v * float(scale)).clip(0.0, 100.0)
    relative = v.groupby(group).rank(pct=True, method="average") * 100.0
    return (absolute * 0.70 + relative * 0.30).where(v.notna())


def score_industry_fundamentals(signal: pd.DataFrame, middle: pd.DataFrame | None = None) -> pd.DataFrame:
    """Create a transparent 0-100 Industry Fundamental Score.

    Components:
      * Export Momentum 30%: 3M average export YoY + 3M acceleration
      * Inventory Cycle 25%: 3M average shipment-minus-inventory + 3M change
      * Real Activity 20%: 3M average shipment and production YoY
      * Breadth 15%: share of research-middle categories with positive export YoY
      * Persistence 10%: six-month share of positive export/inventory-cycle signals

    This is a fundamental screening score. It intentionally excludes stock price, EPS,
    revisions and investor flow until the company/Quanti phase.
    """
    if signal.empty:
        return signal.copy()

    out = signal.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.sort_values(["item20", "date"]).reset_index(drop=True)

    metric_cols = [
        "export_yoy", "inventory_cycle", "shipment_yoy", "production_yoy",
    ]
    for col in metric_cols:
        out[col] = pd.to_numeric(out.get(col), errors="coerce")

    g = out.groupby("item20", group_keys=False)
    out["export_yoy_3m"] = g["export_yoy"].transform(lambda x: x.rolling(3, min_periods=1).mean())
    out["export_accel_3m"] = out["export_yoy"] - g["export_yoy"].shift(3)
    out["inventory_cycle_3m"] = g["inventory_cycle"].transform(lambda x: x.rolling(3, min_periods=1).mean())
    out["inventory_cycle_delta_3m"] = out["inventory_cycle"] - g["inventory_cycle"].shift(3)
    out["shipment_yoy_3m"] = g["shipment_yoy"].transform(lambda x: x.rolling(3, min_periods=1).mean())
    out["production_yoy_3m"] = g["production_yoy"].transform(lambda x: x.rolling(3, min_periods=1).mean())

    # Breadth: how widely export improvement is distributed inside each Top20 industry.
    out["breadth_pct"] = np.nan
    if isinstance(middle, pd.DataFrame) and not middle.empty and {"date", "item20", "yoy_pct"}.issubset(middle.columns):
        b = middle[["date", "item20", "yoy_pct"]].copy()
        b["date"] = pd.to_datetime(b["date"], errors="coerce")
        b["yoy_pct"] = pd.to_numeric(b["yoy_pct"], errors="coerce")
        b = b.dropna(subset=["date", "item20", "yoy_pct"])
        if not b.empty:
            breadth = (
                b.assign(_positive=(b["yoy_pct"] > 0).astype(float))
                .groupby(["date", "item20"], as_index=False)["_positive"].mean()
                .rename(columns={"_positive": "breadth_pct"})
            )
            breadth["breadth_pct"] *= 100.0
            out = out.drop(columns=["breadth_pct"]).merge(breadth, on=["date", "item20"], how="left")

    # Persistence: sustained positive export and inventory-cycle signals, not a single-month spike.
    export_pos = (out["export_yoy"] > 0).where(out["export_yoy"].notna()).astype(float)
    cycle_pos = (out["inventory_cycle"] > 0).where(out["inventory_cycle"].notna()).astype(float)
    out["_month_strength"] = pd.concat([export_pos, cycle_pos], axis=1).mean(axis=1, skipna=True)
    out["persistence_pct"] = (
        out.groupby("item20")["_month_strength"]
        .transform(lambda x: x.rolling(6, min_periods=1).mean()) * 100.0
    )

    # Component scores: 70% absolute condition + 30% cross-sectional rank.
    month_group = out["date"]
    export_level = _absolute_rank_score(out["export_yoy_3m"], scale=2.0, group=month_group)
    export_accel = _absolute_rank_score(out["export_accel_3m"], scale=2.5, group=month_group)
    out["export_momentum_score"] = export_level * 0.65 + export_accel.fillna(export_level) * 0.35

    cycle_level = _absolute_rank_score(out["inventory_cycle_3m"], scale=2.5, group=month_group)
    cycle_delta = _absolute_rank_score(out["inventory_cycle_delta_3m"], scale=3.0, group=month_group)
    out["inventory_cycle_score"] = cycle_level * 0.70 + cycle_delta.fillna(cycle_level) * 0.30

    shipment_score = _absolute_rank_score(out["shipment_yoy_3m"], scale=2.5, group=month_group)
    production_score = _absolute_rank_score(out["production_yoy_3m"], scale=2.5, group=month_group)
    out["real_activity_score"] = shipment_score * 0.60 + production_score * 0.40

    out["breadth_score"] = pd.to_numeric(out["breadth_pct"], errors="coerce").clip(0, 100)
    out["persistence_score"] = pd.to_numeric(out["persistence_pct"], errors="coerce").clip(0, 100)

    components = {
        "export_momentum_score": 0.30,
        "inventory_cycle_score": 0.25,
        "real_activity_score": 0.20,
        "breadth_score": 0.15,
        "persistence_score": 0.10,
    }
    num = pd.Series(0.0, index=out.index)
    den = pd.Series(0.0, index=out.index)
    for col, weight in components.items():
        valid = out[col].notna()
        num += out[col].fillna(0.0) * weight
        den += valid.astype(float) * weight
    score = num.div(den.replace(0, np.nan)).clip(0, 100)

    notes = [[] for _ in range(len(out))]
    joint_weak = (out["export_yoy"] < 0) & (out["inventory_cycle"] < 0)
    score = score.where(~joint_weak, score.clip(upper=50.0))
    for i in out.index[joint_weak]:
        notes[i].append("수출·재고순환 동반 약세")

    narrow = out["breadth_pct"].notna() & (out["breadth_pct"] < 30.0)
    score = score - narrow.astype(float) * 8.0
    for i in out.index[narrow]:
        notes[i].append("중분류 확산도 낮음")

    decel = (out["export_accel_3m"] < 0) & (out["inventory_cycle_delta_3m"] < 0)
    score = score - decel.astype(float) * 5.0
    for i in out.index[decel]:
        notes[i].append("최근 모멘텀 둔화")

    broad = (
        out["breadth_pct"].fillna(0) >= 60
    ) & (
        out["persistence_pct"].fillna(0) >= 60
    ) & (out["export_yoy"] > 0) & (out["inventory_cycle"] > 0)
    for i in out.index[broad]:
        if not notes[i]:
            notes[i].append("광범위·지속 개선")

    out["fundamental_score"] = score.clip(0, 100).round(1)
    # Backward-compatible alias for old marts/app code. UI no longer calls it Industry Score.
    out["industry_score"] = out["fundamental_score"]
    out["score_note"] = [" · ".join(x) if x else "혼조/중립" for x in notes]

    score_cols = [
        "export_momentum_score", "inventory_cycle_score", "real_activity_score",
        "breadth_score", "persistence_score", "breadth_pct", "persistence_pct",
    ]
    for col in score_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").round(1)

    return out.drop(columns=["_month_strength"], errors="ignore")


def build_industry_signal(top20: pd.DataFrame, cycle: pd.DataFrame, bridge_path: str | Path, middle: pd.DataFrame | None = None) -> pd.DataFrame:
    empty = pd.DataFrame(columns=[
        "date", "item20", "export_usd", "export_yoy", "export_mom",
        "production_yoy", "shipment_yoy", "inventory_yoy", "inventory_cycle",
        "export_momentum_score", "inventory_cycle_score", "real_activity_score",
        "breadth_score", "persistence_score", "breadth_pct", "persistence_pct",
        "fundamental_score", "industry_score", "score_note", "stage"
    ])
    p = Path(bridge_path)
    if top20.empty or cycle.empty or not p.exists():
        return empty
    bridge = pd.read_csv(p)
    bridge["ksic_code"] = bridge["ksic_code"].astype(str)
    bridge["weight"] = pd.to_numeric(bridge.get("weight", 1.0), errors="coerce").fillna(1.0)
    cyc = bridge.merge(cycle, on="ksic_code", how="inner")
    if cyc.empty:
        return empty
    metrics = ["production_yoy", "shipment_yoy", "inventory_yoy", "inventory_cycle"]
    for m in metrics:
        cyc[f"_{m}_w"] = pd.to_numeric(cyc[m], errors="coerce") * cyc["weight"]
        cyc[f"_{m}_weight"] = np.where(pd.notna(cyc[m]), cyc["weight"], 0.0)
    agg_dict = {}
    for m in metrics:
        agg_dict[f"_{m}_w"] = (f"_{m}_w", "sum")
        agg_dict[f"_{m}_weight"] = (f"_{m}_weight", "sum")
    grouped = cyc.groupby(["date", "export_item"], as_index=False).agg(**agg_dict)
    for m in metrics:
        grouped[m] = grouped[f"_{m}_w"].div(grouped[f"_{m}_weight"].replace(0, np.nan))
    grouped = grouped[["date", "export_item"] + metrics].rename(columns={"export_item": "item20"})
    exp = top20[["date", "item20", "export_usd", "yoy_pct", "mom_pct"]].rename(columns={"yoy_pct": "export_yoy", "mom_pct": "export_mom"})
    out = exp.merge(grouped, on=["date", "item20"], how="inner")
    if out.empty:
        return out
    out["stage"] = [_lifecycle(s, i) for s, i in zip(out["shipment_yoy"], out["inventory_yoy"])]
    out = score_industry_fundamentals(out, middle)
    return out.sort_values(["date", "fundamental_score"], ascending=[True, False]).reset_index(drop=True)


def _write_table(con: sqlite3.Connection, name: str, df: pd.DataFrame, index_cols: list[str] | None = None) -> None:
    x = df.copy()
    if "date" in x.columns:
        x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    x.to_sql(name, con, if_exists="replace", index=False)
    if index_cols:
        cols = ",".join(index_cols)
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_{name}_main ON {name}({cols})")


def build_analysis_mart(
    raw_db_path: str | Path,
    mart_db_path: str | Path,
    taxonomy_csv_path: str | Path,
    kosis_cache_path: str | Path,
    bridge_csv_path: str | Path,
) -> dict:
    raw_db = Path(raw_db_path)
    mart_db = Path(mart_db_path)
    if not raw_db.exists():
        raise FileNotFoundError(raw_db)
    taxonomy = load_taxonomy(taxonomy_csv_path)
    # One heavy raw-item join at the representative-product grain; higher levels
    # are rolled up from that compact result to keep the one-time build fast.
    product = _sql_aggregate(raw_db, taxonomy, ["item20", "middle_category", "product"])
    middle = _rollup_trade(product, ["item20", "middle_category"])
    top20 = _rollup_trade(product, ["item20"])
    total = _total_and_coverage(raw_db)
    country = _product_country(raw_db)
    cycle = build_kosis_cycle(kosis_cache_path)
    signal = build_industry_signal(top20, cycle, bridge_csv_path, middle)

    mart_db.parent.mkdir(parents=True, exist_ok=True)
    if mart_db.exists():
        mart_db.unlink()
    with sqlite3.connect(mart_db) as con:
        _write_table(con, "dim_product_taxonomy", taxonomy, ["hsk10"])
        _write_table(con, "mart_export_top20_monthly", top20, ["date", "item20"])
        _write_table(con, "mart_export_middle_monthly", middle, ["date", "item20", "middle_category"])
        _write_table(con, "mart_export_product_monthly", product, ["date", "item20", "middle_category", "product"])
        _write_table(con, "mart_export_total_monthly", total, ["date"])
        _write_table(con, "mart_product_country_monthly", country, ["date", "item20", "middle_category", "product", "country_code"])
        _write_table(con, "mart_kosis_cycle_monthly", cycle, ["date", "ksic_code"])
        _write_table(con, "mart_industry_signal_monthly", signal, ["date", "item20"])
        meta = pd.DataFrame([
            {"key": "built_at", "value": datetime.now().isoformat(timespec="seconds")},
            {"key": "latest_export_month", "value": top20["date"].max().strftime("%Y-%m") if not top20.empty else ""},
            {"key": "earliest_export_month", "value": top20["date"].min().strftime("%Y-%m") if not top20.empty else ""},
            {"key": "latest_kosis_month", "value": cycle["date"].max().strftime("%Y-%m") if not cycle.empty else ""},
            {"key": "taxonomy_hsk10", "value": str(taxonomy["hsk10"].nunique())},
            {"key": "taxonomy_middle", "value": str(taxonomy["middle_category"].nunique())},
            {"key": "taxonomy_product", "value": str(taxonomy["product"].nunique())},
        ])
        _write_table(con, "mart_metadata", meta, ["key"])
        con.commit()
    return {
        "top20_rows": len(top20),
        "middle_rows": len(middle),
        "product_rows": len(product),
        "country_rows": len(country),
        "cycle_rows": len(cycle),
        "signal_rows": len(signal),
        "mart_path": str(mart_db),
    }


def mart_status(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"ready": False, "path": str(p)}
    try:
        with sqlite3.connect(p) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            required = {"mart_export_top20_monthly", "dim_product_taxonomy", "mart_metadata"}
            if not required.issubset(tables):
                return {"ready": False, "path": str(p)}
            meta = dict(con.execute("SELECT key,value FROM mart_metadata").fetchall())
            rows = con.execute("SELECT COUNT(*) FROM mart_export_top20_monthly").fetchone()[0]
        return {"ready": True, "path": str(p), "rows": rows, **meta}
    except Exception as exc:
        return {"ready": False, "path": str(p), "error": str(exc)}


def make_share_snapshot(mart_db_path: str | Path, share_path: str | Path) -> Path:
    src = Path(mart_db_path)
    dst = Path(share_path)
    if not mart_status(src).get("ready"):
        raise RuntimeError("Analysis mart is not ready")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst
