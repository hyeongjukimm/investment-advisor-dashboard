from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import pandas as pd
import requests

API_ENDPOINTS = {
    "item": "https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList",
    "country": "https://apis.data.go.kr/1220000/nationtrade/getNationtradeList",
    "item_country": "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList",
}


def decode_service_key(value: str) -> str:
    value = (value or "").strip()
    return unquote(value) if "%" in value else value


def parse_customs_xml(content: bytes | str) -> list[dict[str, str]]:
    if isinstance(content, str):
        content = content.encode("utf-8")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        preview = content[:160].decode("utf-8", errors="replace").replace("\n", " ").strip()
        raise RuntimeError(f"Customs API returned non-XML response: {preview}") from exc

    # data.go.kr gateway authentication/authorization failures use a different
    # envelope from normal API responses.  Treat them as explicit errors rather
    # than silently returning an empty dataset.
    gateway_error = (root.findtext(".//errMsg") or "").strip()
    gateway_auth = (root.findtext(".//returnAuthMsg") or "").strip()
    gateway_reason = (root.findtext(".//returnReasonCode") or "").strip()
    if gateway_error or gateway_auth:
        msg = gateway_error or gateway_auth
        suffix = f" (reason {gateway_reason})" if gateway_reason else ""
        raise RuntimeError(f"Customs API gateway error: {msg}{suffix}")

    result_code = (root.findtext(".//resultCode") or "").strip()
    result_msg = (root.findtext(".//resultMsg") or "").strip()
    if result_code and result_code != "00":
        raise RuntimeError(f"Customs API error {result_code}: {result_msg}")
    rows: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        rows.append({child.tag: (child.text or "").strip() for child in list(item)})
    return rows


def _to_month(value: str) -> pd.Timestamp:
    s = str(value or "").strip()
    if not s or s in {"총계", "total", "Total"}:
        return pd.NaT
    s = s.replace(".", "").replace("-", "")[:6]
    return pd.to_datetime(s, format="%Y%m", errors="coerce")


def _num(value) -> float:
    return pd.to_numeric(str(value or "0").replace(",", ""), errors="coerce")


def normalize_itemtrade(rows: Iterable[dict[str, str]]) -> pd.DataFrame:
    out = []
    for r in rows:
        dt = _to_month(r.get("year", ""))
        hsk = str(r.get("hsCode", "")).strip()
        if pd.isna(dt) or not hsk or hsk == "-":
            continue
        out.append({
            "date": dt,
            "hsk10": hsk.zfill(10),
            "hsk_name": str(r.get("statKor", "")).strip(),
            "export_usd": _num(r.get("expDlr")),
            "export_weight": _num(r.get("expWgt")),
            "import_usd": _num(r.get("impDlr")),
            "import_weight": _num(r.get("impWgt")),
            "balance_usd": _num(r.get("balPayments")),
        })
    return pd.DataFrame(out)


def normalize_countrytrade(rows: Iterable[dict[str, str]]) -> pd.DataFrame:
    out = []
    for r in rows:
        dt = _to_month(r.get("year", ""))
        code = str(r.get("statCd", "")).strip()
        if pd.isna(dt) or not code or code == "-":
            continue
        out.append({
            "date": dt,
            "country_code": code,
            "country_name": str(r.get("statCdCntnKor1", "")).strip(),
            "export_count": _num(r.get("expCnt")),
            "export_usd": _num(r.get("expDlr")),
            "import_count": _num(r.get("impCnt")),
            "import_usd": _num(r.get("impDlr")),
            "balance_usd": _num(r.get("balPayments")),
        })
    return pd.DataFrame(out)


def normalize_item_country(rows: Iterable[dict[str, str]]) -> pd.DataFrame:
    out = []
    for r in rows:
        dt = _to_month(r.get("year", ""))
        code = str(r.get("statCd", "")).strip()
        hsk = str(r.get("hsCd", r.get("hsCode", ""))).strip()
        if pd.isna(dt) or not code or code == "-" or not hsk or hsk == "-":
            continue
        out.append({
            "date": dt,
            "country_code": code,
            "hsk10": hsk.zfill(10),
            "hsk_name": str(r.get("statKor", "")).strip(),
            "export_usd": _num(r.get("expDlr")),
            "export_weight": _num(r.get("expWgt")),
            "import_usd": _num(r.get("impDlr")),
            "import_weight": _num(r.get("impWgt")),
            "balance_usd": _num(r.get("balPayments")),
        })
    return pd.DataFrame(out)


def standardize_mapping(mapping: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "20대품목": "item20",
        "산업부20대품목": "item20",
        "중분류": "middle_category",
        "세부분류": "sub_category",
        "MTI6": "mti6",
        "HSK10": "hsk10",
        "HSK코드": "hsk10",
        "HS6": "hs6",
        "HS4": "hs4",
        "HSK 품목명": "mapping_name",
        "HSK품목명": "mapping_name",
    }
    m = mapping.rename(columns={k: v for k, v in rename.items() if k in mapping.columns}).copy()
    required = ["hsk10", "item20", "mti6"]
    missing = [c for c in required if c not in m.columns]
    if missing:
        raise ValueError(f"Mapping missing columns: {missing}")
    for c in ["hsk10", "mti6", "hs6", "hs4"]:
        if c in m.columns:
            m[c] = m[c].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    m["hsk10"] = m["hsk10"].str.zfill(10)
    for c in ["middle_category", "sub_category", "hs6", "hs4", "mapping_name"]:
        if c not in m.columns:
            m[c] = ""
    return m[["hsk10", "item20", "middle_category", "sub_category", "mti6", "hs6", "hs4", "mapping_name"]].drop_duplicates("hsk10")


def aggregate_top20(item_df: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    if item_df.empty:
        return pd.DataFrame(columns=["date", "item20", "middle_category", "sub_category", "mti6", "hs6", "hs4", "export_usd"])
    m = standardize_mapping(mapping)
    x = item_df.copy()
    x["hsk10"] = x["hsk10"].astype(str).str.zfill(10)
    merged = x.merge(m, on="hsk10", how="inner")
    group_cols = ["date", "item20", "middle_category", "sub_category", "mti6", "hs6", "hs4"]
    return merged.groupby(group_cols, dropna=False, as_index=False)["export_usd"].sum()


def compute_monthly_metrics(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["export_usd"] = pd.to_numeric(out["export_usd"], errors="coerce")
    out = out.sort_values(group_cols + ["date"]).reset_index(drop=True)

    prev_m = out[group_cols + ["date", "export_usd"]].copy()
    prev_m["date"] = prev_m["date"] + pd.DateOffset(months=1)
    prev_m = prev_m.rename(columns={"export_usd": "_prev_m"})

    prev_y = out[group_cols + ["date", "export_usd"]].copy()
    prev_y["date"] = prev_y["date"] + pd.DateOffset(months=12)
    prev_y = prev_y.rename(columns={"export_usd": "_prev_y"})

    out = out.merge(prev_m, on=group_cols + ["date"], how="left")
    out = out.merge(prev_y, on=group_cols + ["date"], how="left")
    out["mom_pct"] = (out["export_usd"] / out["_prev_m"] - 1) * 100
    out["yoy_pct"] = (out["export_usd"] / out["_prev_y"] - 1) * 100
    out["year"] = out["date"].dt.year
    out["ytd_usd"] = out.groupby(group_cols + ["year"], dropna=False)["export_usd"].cumsum()
    return out.drop(columns=["_prev_m", "_prev_y"])


def parse_history_start(value: str | pd.Timestamp | None, target_month: pd.Timestamp) -> pd.Timestamp | None:
    """Parse a configurable history floor and clamp it to the target month."""
    if value is None or str(value).strip() == "":
        return None
    target = pd.Timestamp(target_month)
    target = pd.Timestamp(target.year, target.month, 1)
    parsed = pd.to_datetime(str(value).strip(), errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid CUSTOMS_HISTORY_START: {value}")
    parsed = pd.Timestamp(parsed.year, parsed.month, 1)
    return min(parsed, target)


def latest_safe_customs_month(today: date | None = None, cutoff_day: int = 16) -> pd.Timestamp:
    today = today or date.today()
    current = pd.Timestamp(today.year, today.month, 1)
    months_back = 1 if today.day >= cutoff_day else 2
    return current - pd.DateOffset(months=months_back)


def iter_month_chunks(start: pd.Timestamp, end: pd.Timestamp, max_months: int = 12):
    cur = pd.Timestamp(start.year, start.month, 1)
    end = pd.Timestamp(end.year, end.month, 1)
    while cur <= end:
        chunk_end = min(cur + pd.DateOffset(months=max_months - 1), end)
        yield cur, chunk_end
        cur = chunk_end + pd.DateOffset(months=1)


def probe_latest_item_data(
    client,
    anchor_month: pd.Timestamp | None = None,
    lookback_months: int = 4,
) -> dict:
    """Fetch a short recent window and infer the latest month actually returned.

    This deliberately does not guess availability from today's calendar date.
    The returned dataframe can be upserted directly, so the probe also refreshes
    recent revisions without a second network call.
    """
    if lookback_months < 1:
        raise ValueError("lookback_months must be >= 1")
    anchor = pd.Timestamp(anchor_month or pd.Timestamp.today())
    anchor = pd.Timestamp(anchor.year, anchor.month, 1)
    start = anchor - pd.DateOffset(months=lookback_months - 1)
    data = normalize_itemtrade(client.fetch("item", start, anchor))
    latest = None if data.empty else pd.Timestamp(data["date"].max())
    if latest is not None:
        latest = pd.Timestamp(latest.year, latest.month, 1)
    return {
        "latest_month": latest,
        "data": data,
        "requested_start": start,
        "requested_end": anchor,
    }


@dataclass
class CustomsClient:
    service_key: str
    verify_ssl: bool = False
    timeout: int = 60

    def __post_init__(self):
        self.service_key = decode_service_key(self.service_key)

    def fetch(self, dataset: str, start: pd.Timestamp, end: pd.Timestamp, country_code: str | None = None, hs_code: str | None = None) -> list[dict[str, str]]:
        if dataset not in API_ENDPOINTS:
            raise ValueError(f"Unknown dataset: {dataset}")
        params = {
            "serviceKey": self.service_key,
            "strtYymm": pd.Timestamp(start).strftime("%Y%m"),
            "endYymm": pd.Timestamp(end).strftime("%Y%m"),
        }
        if country_code:
            params["cntyCd"] = country_code
        if hs_code:
            params["hsSgn"] = hs_code
        if dataset == "item_country" and not (country_code or hs_code):
            raise ValueError("item_country requires country_code or hs_code")
        resp = requests.get(API_ENDPOINTS[dataset], params=params, timeout=self.timeout, verify=self.verify_ssl)
        resp.raise_for_status()
        return parse_customs_xml(resp.content)

# -----------------------------------------------------------------------------
# Portable local store (SQLite). The schema is deliberately DuckDB-compatible
# enough to migrate later without changing dashboard-facing column names.
# -----------------------------------------------------------------------------
import sqlite3


def init_sqlite_db(db_path: str | Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS raw_item (
                date TEXT NOT NULL,
                hsk10 TEXT NOT NULL,
                hsk_name TEXT,
                export_usd REAL,
                export_weight REAL,
                import_usd REAL,
                import_weight REAL,
                balance_usd REAL,
                PRIMARY KEY (date, hsk10)
            );
            CREATE TABLE IF NOT EXISTS raw_country (
                date TEXT NOT NULL,
                country_code TEXT NOT NULL,
                country_name TEXT,
                export_count REAL,
                export_usd REAL,
                import_count REAL,
                import_usd REAL,
                balance_usd REAL,
                PRIMARY KEY (date, country_code)
            );
            CREATE TABLE IF NOT EXISTS raw_item_country (
                date TEXT NOT NULL,
                country_code TEXT NOT NULL,
                hsk10 TEXT NOT NULL,
                hsk_name TEXT,
                export_usd REAL,
                export_weight REAL,
                import_usd REAL,
                import_weight REAL,
                balance_usd REAL,
                PRIMARY KEY (date, country_code, hsk10)
            );
            CREATE TABLE IF NOT EXISTS dim_hsk_mti20 (
                hsk10 TEXT PRIMARY KEY,
                item20 TEXT NOT NULL,
                middle_category TEXT,
                sub_category TEXT,
                mti6 TEXT,
                hs6 TEXT,
                hs4 TEXT,
                mapping_name TEXT
            );
            CREATE TABLE IF NOT EXISTS refresh_meta (
                dataset TEXT PRIMARY KEY,
                last_success_at TEXT,
                last_data_month TEXT,
                row_count INTEGER,
                note TEXT
            );
            """
        )


def _prep_for_sql(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    if "date" in x.columns:
        x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return x.where(pd.notna(x), None)


def upsert_dataframe(db_path: str | Path, table: str, df: pd.DataFrame, key_cols: list[str]) -> None:
    if df.empty:
        return
    init_sqlite_db(db_path)
    x = _prep_for_sql(df)
    columns = list(x.columns)
    with sqlite3.connect(db_path) as con:
        con.execute("BEGIN")
        try:
            placeholders = ",".join(["?"] * len(columns))
            col_sql = ",".join([f'"{c}"' for c in columns])
            sql = f'INSERT OR REPLACE INTO "{table}" ({col_sql}) VALUES ({placeholders})'
            con.executemany(sql, x.itertuples(index=False, name=None))
            con.commit()
        except Exception:
            con.rollback()
            raise


def save_mapping(db_path: str | Path, mapping: pd.DataFrame) -> None:
    init_sqlite_db(db_path)
    m = standardize_mapping(mapping)
    with sqlite3.connect(db_path) as con:
        con.execute("DELETE FROM dim_hsk_mti20")
        m.to_sql("dim_hsk_mti20", con, if_exists="append", index=False)


def _read_sql_dates(db_path: str | Path, sql: str, params=()) -> pd.DataFrame:
    init_sqlite_db(db_path)
    with sqlite3.connect(db_path) as con:
        df = pd.read_sql_query(sql, con, params=params)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def query_top20_monthly(db_path: str | Path) -> pd.DataFrame:
    base = _read_sql_dates(
        db_path,
        """
        SELECT r.date, m.item20, SUM(r.export_usd) AS export_usd
        FROM raw_item r
        JOIN dim_hsk_mti20 m ON r.hsk10 = m.hsk10
        GROUP BY r.date, m.item20
        ORDER BY r.date, m.item20
        """,
    )
    return compute_monthly_metrics(base, ["item20"])


def query_top20_detail_monthly(db_path: str | Path, item20: str | None = None) -> pd.DataFrame:
    sql = """
        SELECT r.date, m.item20, m.middle_category, m.sub_category, m.mti6,
               m.hs6, m.hs4, SUM(r.export_usd) AS export_usd
        FROM raw_item r
        JOIN dim_hsk_mti20 m ON r.hsk10 = m.hsk10
    """
    params = []
    if item20:
        sql += " WHERE m.item20 = ?"
        params.append(item20)
    sql += " GROUP BY r.date, m.item20, m.middle_category, m.sub_category, m.mti6, m.hs6, m.hs4 ORDER BY r.date, m.item20, m.mti6"
    return _read_sql_dates(db_path, sql, params)


def query_top20_country_monthly(db_path: str | Path, item20: str | None = None, country_code: str | None = None) -> pd.DataFrame:
    sql = """
        SELECT r.date, r.country_code, m.item20, SUM(r.export_usd) AS export_usd
        FROM raw_item_country r
        JOIN dim_hsk_mti20 m ON r.hsk10 = m.hsk10
        WHERE 1=1
    """
    params = []
    if item20:
        sql += " AND m.item20 = ?"
        params.append(item20)
    if country_code:
        sql += " AND r.country_code = ?"
        params.append(country_code)
    sql += " GROUP BY r.date, r.country_code, m.item20 ORDER BY r.date, r.country_code, m.item20"
    return _read_sql_dates(db_path, sql, params)


def query_country_monthly(db_path: str | Path) -> pd.DataFrame:
    return _read_sql_dates(db_path, "SELECT * FROM raw_country ORDER BY date, country_code")


def query_mapping_coverage_monthly(db_path: str | Path) -> pd.DataFrame:
    """Monthly value/row coverage of the fixed 2026 HSK10→Top20 taxonomy."""
    return _read_sql_dates(
        db_path,
        """
        SELECT r.date,
               SUM(COALESCE(r.export_usd,0)) AS total_export_usd,
               SUM(CASE WHEN m.hsk10 IS NOT NULL THEN COALESCE(r.export_usd,0) ELSE 0 END) AS mapped_export_usd,
               SUM(CASE WHEN m.hsk10 IS NULL THEN COALESCE(r.export_usd,0) ELSE 0 END) AS unmapped_export_usd,
               COUNT(*) AS raw_hsk_rows,
               SUM(CASE WHEN m.hsk10 IS NOT NULL THEN 1 ELSE 0 END) AS mapped_hsk_rows,
               COUNT(DISTINCT CASE WHEN m.hsk10 IS NOT NULL THEN m.item20 END) AS mapped_categories
        FROM raw_item r
        LEFT JOIN dim_hsk_mti20 m ON r.hsk10=m.hsk10
        GROUP BY r.date
        ORDER BY r.date
        """,
    ).assign(
        mapped_value_pct=lambda d: d["mapped_export_usd"].div(d["total_export_usd"].replace(0, pd.NA)).mul(100),
        mapped_row_pct=lambda d: d["mapped_hsk_rows"].div(d["raw_hsk_rows"].replace(0, pd.NA)).mul(100),
    )


def query_unmapped_hsk(db_path: str | Path, target_month: pd.Timestamp | None = None, limit: int = 100) -> pd.DataFrame:
    """Largest HS10 rows not represented by the fixed 2026 mapping."""
    sql = """
        SELECT r.hsk10, MAX(COALESCE(r.hsk_name,'')) AS hsk_name, SUM(COALESCE(r.export_usd,0)) AS export_usd
        FROM raw_item r
        LEFT JOIN dim_hsk_mti20 m ON r.hsk10=m.hsk10
        WHERE m.hsk10 IS NULL
    """
    params = []
    if target_month is not None:
        t = pd.Timestamp(target_month)
        sql += " AND r.date=?"
        params.append(pd.Timestamp(t.year, t.month, 1).strftime("%Y-%m-%d"))
    sql += " GROUP BY r.hsk10 ORDER BY export_usd DESC LIMIT ?"
    params.append(int(limit))
    return _read_sql_dates(db_path, sql, params)


def query_top20_coverage(db_path: str | Path, target_month: pd.Timestamp) -> dict:
    """Return a strict category-presence gate for one month.

    A month is PASS only when every category present in the mapping dimension is
    represented by at least one returned HSK row for that month.
    """
    init_sqlite_db(db_path)
    target = pd.Timestamp(target_month)
    target = pd.Timestamp(target.year, target.month, 1).strftime("%Y-%m-%d")
    with sqlite3.connect(db_path) as con:
        expected = [r[0] for r in con.execute(
            "SELECT DISTINCT item20 FROM dim_hsk_mti20 WHERE item20 IS NOT NULL AND item20 <> '' ORDER BY item20"
        ).fetchall()]
        observed = [r[0] for r in con.execute(
            """
            SELECT DISTINCT m.item20
            FROM raw_item r
            JOIN dim_hsk_mti20 m ON r.hsk10=m.hsk10
            WHERE r.date=?
            ORDER BY m.item20
            """,
            (target,),
        ).fetchall()]
        raw_hsk_rows = con.execute("SELECT COUNT(*) FROM raw_item WHERE date=?", (target,)).fetchone()[0]
        mapped_hsk_rows = con.execute(
            """SELECT COUNT(*) FROM raw_item r JOIN dim_hsk_mti20 m ON r.hsk10=m.hsk10 WHERE r.date=?""",
            (target,),
        ).fetchone()[0]
    missing = sorted(set(expected) - set(observed))
    return {
        "month": target[:7],
        "expected_count": len(expected),
        "observed_count": len(observed),
        "missing_items": missing,
        "status": "PASS" if expected and not missing and len(observed) == len(expected) else "FAIL",
        "raw_hsk_rows": int(raw_hsk_rows),
        "mapped_hsk_rows": int(mapped_hsk_rows),
    }


def query_latest_full20_month(db_path: str | Path) -> pd.Timestamp | None:
    """Latest month that passes the complete mapped-category presence gate."""
    init_sqlite_db(db_path)
    with sqlite3.connect(db_path) as con:
        expected = con.execute(
            "SELECT COUNT(DISTINCT item20) FROM dim_hsk_mti20 WHERE item20 IS NOT NULL AND item20 <> ''"
        ).fetchone()[0]
        if not expected:
            return None
        row = con.execute(
            """
            SELECT r.date
            FROM raw_item r
            JOIN dim_hsk_mti20 m ON r.hsk10=m.hsk10
            GROUP BY r.date
            HAVING COUNT(DISTINCT m.item20)=?
            ORDER BY r.date DESC
            LIMIT 1
            """,
            (expected,),
        ).fetchone()
    return pd.Timestamp(row[0]) if row and row[0] else None


def resolve_display_month(db_path: str | Path, detected_month: pd.Timestamp | None = None) -> dict:
    """Choose the month safe to present as a complete 20-item panel.

    The newest month discovered from Customs is promoted immediately only when
    the strict 20/20 category-presence gate passes.  If a newly-published month
    is still partial, the dashboard keeps the latest prior full month while
    exposing the detected partial month and its missing categories for QC.
    """
    detected = None
    if detected_month is not None and not pd.isna(detected_month):
        d = pd.Timestamp(detected_month)
        detected = pd.Timestamp(d.year, d.month, 1)

    detected_coverage = query_top20_coverage(db_path, detected) if detected is not None else None
    latest_full = query_latest_full20_month(db_path)
    if latest_full is not None:
        latest_full = pd.Timestamp(latest_full.year, latest_full.month, 1)

    use_detected = bool(
        detected is not None
        and detected_coverage is not None
        and detected_coverage.get("status") == "PASS"
        and latest_full is not None
        and detected == latest_full
    )

    return {
        "detected_month": detected,
        "detected_coverage": detected_coverage,
        "display_month": latest_full,
        "using_detected_month": use_detected,
    }


def query_db_status(db_path: str | Path) -> dict:
    init_sqlite_db(db_path)
    with sqlite3.connect(db_path) as con:
        item_rows = con.execute("SELECT COUNT(*) FROM raw_item").fetchone()[0]
        country_rows = con.execute("SELECT COUNT(*) FROM raw_country").fetchone()[0]
        item_country_rows = con.execute("SELECT COUNT(*) FROM raw_item_country").fetchone()[0]
        mapping_rows = con.execute("SELECT COUNT(*) FROM dim_hsk_mti20").fetchone()[0]
        max_item = con.execute("SELECT MAX(date) FROM raw_item").fetchone()[0]
        max_country = con.execute("SELECT MAX(date) FROM raw_country").fetchone()[0]
        meta = pd.read_sql_query("SELECT * FROM refresh_meta ORDER BY dataset", con)
    return {
        "item_rows": item_rows,
        "country_rows": country_rows,
        "item_country_rows": item_country_rows,
        "mapping_rows": mapping_rows,
        "max_item_date": max_item,
        "max_country_date": max_country,
        "meta": meta,
    }


def _table_max_date(db_path: str | Path, table: str, where: str = "", params=()) -> pd.Timestamp | None:
    init_sqlite_db(db_path)
    sql = f'SELECT MAX(date) FROM "{table}"'
    if where:
        sql += " WHERE " + where
    with sqlite3.connect(db_path) as con:
        value = con.execute(sql, params).fetchone()[0]
    return pd.to_datetime(value, errors="coerce") if value else None


def _table_min_date(db_path: str | Path, table: str, where: str = "", params=()) -> pd.Timestamp | None:
    init_sqlite_db(db_path)
    sql = f'SELECT MIN(date) FROM "{table}"'
    if where:
        sql += " WHERE " + where
    with sqlite3.connect(db_path) as con:
        value = con.execute(sql, params).fetchone()[0]
    return pd.to_datetime(value, errors="coerce") if value else None


def _history_backfill_range(min_date: pd.Timestamp | None, history_floor: pd.Timestamp | None, target: pd.Timestamp):
    if history_floor is None:
        return None
    floor = pd.Timestamp(history_floor.year, history_floor.month, 1)
    target = pd.Timestamp(target.year, target.month, 1)
    if min_date is None or pd.isna(min_date):
        return floor, target
    current_min = pd.Timestamp(min_date.year, min_date.month, 1)
    if current_min <= floor:
        return None
    return floor, current_min - pd.DateOffset(months=1)


def _refresh_start(max_date: pd.Timestamp | None, target: pd.Timestamp, bootstrap_months: int, force: bool) -> pd.Timestamp:
    target = pd.Timestamp(target.year, target.month, 1)
    if force or max_date is None or pd.isna(max_date):
        return target - pd.DateOffset(months=bootstrap_months - 1)
    return min(pd.Timestamp(max_date.year, max_date.month, 1) - pd.DateOffset(months=2), target)


def _update_meta(db_path: str | Path, dataset: str, last_data_month: pd.Timestamp | None, row_count: int, note: str = "") -> None:
    from datetime import datetime
    init_sqlite_db(db_path)
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT OR REPLACE INTO refresh_meta(dataset,last_success_at,last_data_month,row_count,note) VALUES (?,?,?,?,?)",
            (
                dataset,
                datetime.now().isoformat(timespec="seconds"),
                pd.Timestamp(last_data_month).strftime("%Y-%m-%d") if last_data_month is not None and not pd.isna(last_data_month) else None,
                int(row_count),
                note,
            ),
        )


def _already_fresh_today(db_path: str | Path, dataset: str, target_month: pd.Timestamp) -> bool:
    from datetime import date as _date
    init_sqlite_db(db_path)
    with sqlite3.connect(db_path) as con:
        row = con.execute("SELECT last_success_at,last_data_month FROM refresh_meta WHERE dataset=?", (dataset,)).fetchone()
    if not row or not row[0] or not row[1]:
        return False
    try:
        return pd.Timestamp(row[0]).date() == _date.today() and pd.Timestamp(row[1]) >= pd.Timestamp(target_month)
    except Exception:
        return False


def refresh_customs_data(
    client: CustomsClient,
    db_path: str | Path,
    mapping: pd.DataFrame,
    target_month: pd.Timestamp | None = None,
    bootstrap_months: int = 36,
    tracked_countries: list[str] | None = None,
    force: bool = False,
    anchor_month: pd.Timestamp | None = None,
    probe_months: int = 4,
    history_start: str | pd.Timestamp | None = None,
    item_country_months: int = 24,
) -> dict:
    """Refresh Customs datasets and promote the latest month actually observed.

    When ``target_month`` is None, the item endpoint itself is probed across a
    short recent window. Any rows returned by that probe are immediately
    upserted, so a newly-published HS month becomes visible on the same app run.
    Subsequent country datasets are requested through that detected month.
    """
    tracked_countries = [c.strip().upper() for c in (tracked_countries or []) if c and c.strip()]
    init_sqlite_db(db_path)
    save_mapping(db_path, mapping)

    previous_item_max = _table_max_date(db_path, "raw_item")
    previous_item_min = _table_min_date(db_path, "raw_item")
    auto_probe = target_month is None
    probe_df = pd.DataFrame()
    probe_info = None

    if auto_probe:
        probe_info = probe_latest_item_data(client, anchor_month=anchor_month, lookback_months=probe_months)
        target_month = probe_info["latest_month"]
        probe_df = probe_info["data"]
        if target_month is None:
            raise RuntimeError(
                f"Customs item probe returned no monthly HS rows for "
                f"{probe_info['requested_start']:%Y-%m}..{probe_info['requested_end']:%Y-%m}"
            )
    else:
        target_month = pd.Timestamp(target_month)

    target_month = pd.Timestamp(target_month.year, target_month.month, 1)
    history_floor = parse_history_start(history_start, target_month)
    previous_label = None if previous_item_max is None or pd.isna(previous_item_max) else pd.Timestamp(previous_item_max).strftime("%Y-%m")
    new_data_detected = bool(previous_item_max is not None and not pd.isna(previous_item_max) and target_month > pd.Timestamp(previous_item_max))

    result = {
        "target_month": target_month.strftime("%Y-%m"),
        "previous_latest_month": previous_label,
        "new_data_detected": new_data_detected,
        "probe_start": probe_info["requested_start"].strftime("%Y-%m") if probe_info else None,
        "probe_end": probe_info["requested_end"].strftime("%Y-%m") if probe_info else None,
        "history_start": history_floor.strftime("%Y-%m") if history_floor is not None else None,
        "datasets": {},
        "skipped": [],
    }

    # HS item universe: auto mode always uses the live probe, even if this app
    # already refreshed earlier today. This is what makes newly-published data
    # visible on the first run of a fresh Streamlit session.
    if auto_probe:
        upsert_dataframe(db_path, "raw_item", probe_df, ["date", "hsk10"])
        collected = len(probe_df)
        # Backfill a configured history floor. If a first build was interrupted,
        # resume only the missing older segment instead of assuming MAX(date) means complete history.
        hist_range = _history_backfill_range(previous_item_min, history_floor, target_month)
        if hist_range is None and (previous_item_max is None or pd.isna(previous_item_max)):
            hist_range = (target_month - pd.DateOffset(months=bootstrap_months - 1), target_month)
        if hist_range is not None:
            start, hist_end = hist_range
            for a, b in iter_month_chunks(start, hist_end, 12):
                df = normalize_itemtrade(client.fetch("item", a, b))
                upsert_dataframe(db_path, "raw_item", df, ["date", "hsk10"])
                collected += len(df)
        current_max = _table_max_date(db_path, "raw_item")
        with sqlite3.connect(db_path) as con:
            rows = con.execute("SELECT COUNT(*) FROM raw_item").fetchone()[0]
        _update_meta(
            db_path,
            "item",
            current_max,
            rows,
            f"live probe {result['probe_start']}..{result['probe_end']}; detected {target_month:%Y-%m}; received {collected}",
        )
        result["datasets"]["item"] = {
            "received": collected,
            "max_date": str(current_max.date()) if current_max is not None else None,
            "probe_received": len(probe_df),
        }
    elif not force and _already_fresh_today(db_path, "item", target_month):
        result["skipped"].append("item")
    else:
        max_date = _table_max_date(db_path, "raw_item")
        start = (history_floor if (force or max_date is None or pd.isna(max_date)) and history_floor is not None
                 else _refresh_start(max_date, target_month, bootstrap_months, force))
        collected = 0
        for a, b in iter_month_chunks(start, target_month, 12):
            df = normalize_itemtrade(client.fetch("item", a, b))
            upsert_dataframe(db_path, "raw_item", df, ["date", "hsk10"])
            collected += len(df)
        current_max = _table_max_date(db_path, "raw_item")
        with sqlite3.connect(db_path) as con:
            rows = con.execute("SELECT COUNT(*) FROM raw_item").fetchone()[0]
        _update_meta(db_path, "item", current_max, rows, f"requested {start:%Y-%m}..{target_month:%Y-%m}; received {collected}")
        result["datasets"]["item"] = {"received": collected, "max_date": str(current_max.date()) if current_max is not None else None}

    # Strict 20-category presence check on the detected month.
    result["coverage"] = query_top20_coverage(db_path, target_month)
    full_month = query_latest_full20_month(db_path)
    result["latest_full20_month"] = full_month.strftime("%Y-%m") if full_month is not None else None

    # country totals
    if not force and _already_fresh_today(db_path, "country", target_month):
        result["skipped"].append("country")
    else:
        max_date = _table_max_date(db_path, "raw_country")
        min_date = _table_min_date(db_path, "raw_country")
        collected = 0
        hist_range = _history_backfill_range(min_date, history_floor, target_month)
        if hist_range is not None:
            a0, b0 = hist_range
            for a, b in iter_month_chunks(a0, b0, 12):
                df = normalize_countrytrade(client.fetch("country", a, b))
                upsert_dataframe(db_path, "raw_country", df, ["date", "country_code"])
                collected += len(df)
        # Always refresh the recent revision window as well.
        recent_start = _refresh_start(max_date, target_month, bootstrap_months, False)
        if hist_range is None or recent_start > hist_range[1]:
            for a, b in iter_month_chunks(recent_start, target_month, 12):
                df = normalize_countrytrade(client.fetch("country", a, b))
                upsert_dataframe(db_path, "raw_country", df, ["date", "country_code"])
                collected += len(df)
        start = hist_range[0] if hist_range is not None else recent_start
        current_max = _table_max_date(db_path, "raw_country")
        with sqlite3.connect(db_path) as con:
            rows = con.execute("SELECT COUNT(*) FROM raw_country").fetchone()[0]
        _update_meta(db_path, "country", current_max, rows, f"requested {start:%Y-%m}..{target_month:%Y-%m}; received {collected}")
        result["datasets"]["country"] = {"received": collected, "max_date": str(current_max.date()) if current_max is not None else None}

    # selected country x HSK universe stays independently bounded because it is an exposure view.
    country_bootstrap = max(15, int(item_country_months))
    for country in tracked_countries:
        dataset_key = f"item_country:{country}"
        if not force and _already_fresh_today(db_path, dataset_key, target_month):
            result["skipped"].append(dataset_key)
            continue
        max_date = _table_max_date(db_path, "raw_item_country", "country_code=?", (country,))
        start = _refresh_start(max_date, target_month, country_bootstrap, force)
        collected = 0
        for a, b in iter_month_chunks(start, target_month, 12):
            df = normalize_item_country(client.fetch("item_country", a, b, country_code=country))
            upsert_dataframe(db_path, "raw_item_country", df, ["date", "country_code", "hsk10"])
            collected += len(df)
        current_max = _table_max_date(db_path, "raw_item_country", "country_code=?", (country,))
        with sqlite3.connect(db_path) as con:
            rows = con.execute("SELECT COUNT(*) FROM raw_item_country WHERE country_code=?", (country,)).fetchone()[0]
        _update_meta(db_path, dataset_key, current_max, rows, f"requested {start:%Y-%m}..{target_month:%Y-%m}; received {collected}")
        result["datasets"][dataset_key] = {"received": collected, "max_date": str(current_max.date()) if current_max is not None else None}

    return result

