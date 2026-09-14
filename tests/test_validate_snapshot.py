import sqlite3
from pathlib import Path

import pytest

from validate_snapshot import SnapshotValidationError, promote_snapshot, validate_snapshot


def _db(path: Path, *, complete: bool = True, rows: int = 1):
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE mart_metadata(key TEXT, value TEXT)")
        con.execute("INSERT INTO mart_metadata VALUES('latest_export_month','2026-08')")
        con.execute("CREATE TABLE dim_product_taxonomy(hsk10 TEXT)")
        if complete:
            con.execute("CREATE TABLE mart_export_top20_monthly(date TEXT, item20 TEXT)")
            con.executemany("INSERT INTO mart_export_top20_monthly VALUES('2026-08-01','반도체')", [()] * rows)


def test_validate_snapshot_rejects_missing_tables_and_empty_top20(tmp_path):
    missing = tmp_path / "missing.sqlite"; _db(missing, complete=False)
    with pytest.raises(SnapshotValidationError): validate_snapshot(missing)
    empty = tmp_path / "empty.sqlite"; _db(empty, rows=0)
    with pytest.raises(SnapshotValidationError): validate_snapshot(empty)


def test_validate_and_promote_preserves_last_good_snapshot_on_failure(tmp_path):
    target = tmp_path / "share.sqlite"; _db(target, rows=2)
    candidate = tmp_path / "candidate.sqlite"; _db(candidate, complete=False)
    before = target.read_bytes()
    with pytest.raises(SnapshotValidationError): promote_snapshot(candidate, target)
    assert target.read_bytes() == before
    good = tmp_path / "good.sqlite"; _db(good, rows=3)
    result = promote_snapshot(good, target)
    assert result["rows"] == 3
    assert validate_snapshot(target)["latest_export_month"] == "2026-08"
