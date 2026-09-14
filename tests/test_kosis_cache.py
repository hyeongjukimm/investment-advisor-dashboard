from pathlib import Path

import pandas as pd

from kosis_cache import read_kosis_cache, write_kosis_cache, cache_status


def test_kosis_cache_round_trip(tmp_path: Path):
    p = tmp_path / "kosis.csv"
    df = pd.DataFrame({"PRD_DE": ["202601", "202602"], "IND_CODE": ["C26", "C26"], "DT_val": [101.2, 103.4]})
    write_kosis_cache(df, p)
    out = read_kosis_cache(p)
    assert out["PRD_DE"].tolist() == ["202601", "202602"]
    assert out["DT_val"].tolist() == [101.2, 103.4]


def test_kosis_cache_status_reports_latest_period_and_rows(tmp_path: Path):
    p = tmp_path / "kosis.csv"
    df = pd.DataFrame({"PRD_DE": ["202512", "202601"], "IND_CODE": ["C26", "C26"], "DT_val": [99.0, 100.0]})
    write_kosis_cache(df, p)
    status = cache_status(p)
    assert status["exists"] is True
    assert status["rows"] == 2
    assert status["latest_period"] == "202601"


def test_kosis_cache_status_for_missing_file(tmp_path: Path):
    status = cache_status(tmp_path / "missing.csv")
    assert status == {"exists": False, "rows": 0, "latest_period": None, "updated_at": None}
