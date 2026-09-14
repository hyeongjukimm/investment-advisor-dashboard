import pandas as pd

import customs_pipeline as cp


def _mapping():
    return pd.DataFrame([
        {"HSK10": "0000000001", "20대품목": "A", "중분류": "A1", "세부분류": "A11", "MTI6": "100001", "HS6": "000001", "HS4": "0000"},
        {"HSK10": "0000000002", "20대품목": "B", "중분류": "B1", "세부분류": "B11", "MTI6": "100002", "HS6": "000002", "HS4": "0000"},
    ])


def test_parse_history_start_accepts_year_month_and_clamps_to_target():
    assert cp.parse_history_start("1988-01", pd.Timestamp("2026-08-01")) == pd.Timestamp("1988-01-01")
    assert cp.parse_history_start("2030-01", pd.Timestamp("2026-08-01")) == pd.Timestamp("2026-08-01")


def test_mapping_coverage_uses_export_value_and_reports_gap(tmp_path):
    db = tmp_path / "coverage.sqlite"
    cp.init_sqlite_db(db)
    cp.save_mapping(db, _mapping())
    rows = pd.DataFrame([
        {"date": pd.Timestamp("2026-08-01"), "hsk10": "0000000001", "hsk_name": "Mapped", "export_usd": 80, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 80},
        {"date": pd.Timestamp("2026-08-01"), "hsk10": "9999999999", "hsk_name": "Unmapped", "export_usd": 20, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 20},
    ])
    cp.upsert_dataframe(db, "raw_item", rows, ["date", "hsk10"])
    cov = cp.query_mapping_coverage_monthly(db)
    row = cov.iloc[-1]
    assert row["total_export_usd"] == 100
    assert row["mapped_export_usd"] == 80
    assert row["unmapped_export_usd"] == 20
    assert row["mapped_value_pct"] == 80
    assert row["mapped_hsk_rows"] == 1


def test_query_unmapped_hsk_ranks_by_export_value(tmp_path):
    db = tmp_path / "unmapped.sqlite"
    cp.init_sqlite_db(db)
    cp.save_mapping(db, _mapping())
    rows = pd.DataFrame([
        {"date": pd.Timestamp("2026-08-01"), "hsk10": "9999999999", "hsk_name": "X", "export_usd": 50, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 50},
        {"date": pd.Timestamp("2026-08-01"), "hsk10": "8888888888", "hsk_name": "Y", "export_usd": 100, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 100},
        {"date": pd.Timestamp("2026-08-01"), "hsk10": "0000000001", "hsk_name": "Mapped", "export_usd": 999, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 999},
    ])
    cp.upsert_dataframe(db, "raw_item", rows, ["date", "hsk10"])
    out = cp.query_unmapped_hsk(db, pd.Timestamp("2026-08-01"), limit=2)
    assert out["hsk10"].tolist() == ["8888888888", "9999999999"]
    assert out["export_usd"].tolist() == [100, 50]

def test_history_backfill_range_resumes_missing_older_segment():
    floor = pd.Timestamp("2020-01-01")
    target = pd.Timestamp("2026-08-01")
    assert cp._history_backfill_range(None, floor, target) == (floor, target)
    assert cp._history_backfill_range(pd.Timestamp("2024-01-01"), floor, target) == (floor, pd.Timestamp("2023-12-01"))
    assert cp._history_backfill_range(pd.Timestamp("2020-01-01"), floor, target) is None
