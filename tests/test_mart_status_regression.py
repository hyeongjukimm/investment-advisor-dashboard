import sqlite3

from mart_builder import mart_status


def test_mart_status_rejects_empty_top20_table(tmp_path):
    db = tmp_path / "empty.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE mart_export_top20_monthly(date TEXT, item20 TEXT)")
        con.execute("CREATE TABLE dim_product_taxonomy(hsk10 TEXT)")
        con.execute("CREATE TABLE mart_metadata(key TEXT, value TEXT)")
    status = mart_status(db)
    assert status["ready"] is False
    assert status["rows"] == 0
