import pandas as pd
from datetime import date

from customs_pipeline import (
    parse_customs_xml,
    normalize_itemtrade,
    normalize_countrytrade,
    normalize_item_country,
    aggregate_top20,
    compute_monthly_metrics,
    latest_safe_customs_month,
)

ITEM_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header><body><items>
<item><year>2026.07</year><hsCode>8542321010</hsCode><statKor>DRAM</statKor><expDlr>100</expDlr><expWgt>2</expWgt><impDlr>3</impDlr><impWgt>1</impWgt><balPayments>97</balPayments></item>
<item><year>2026.07</year><hsCode>8703231000</hsCode><statKor>Passenger car</statKor><expDlr>200</expDlr><expWgt>4</expWgt><impDlr>5</impDlr><impWgt>1</impWgt><balPayments>195</balPayments></item>
<item><year>total</year><hsCode>-</hsCode><statKor>-</statKor><expDlr>300</expDlr><expWgt>6</expWgt><impDlr>8</impDlr><impWgt>2</impWgt><balPayments>292</balPayments></item>
</items></body></response>'''

COUNTRY_XML = b'''<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header><body><items>
<item><year>2026.07</year><statCd>US</statCd><statCdCntnKor1>United States</statCdCntnKor1><expCnt>10</expCnt><expDlr>500</expDlr><impCnt>20</impCnt><impDlr>400</impDlr><balPayments>100</balPayments></item>
<item><year>total</year><statCd>-</statCd><statCdCntnKor1>-</statCdCntnKor1><expCnt>10</expCnt><expDlr>500</expDlr><impCnt>20</impCnt><impDlr>400</impDlr><balPayments>100</balPayments></item>
</items></body></response>'''

ITEM_COUNTRY_XML = b'''<response><header><resultCode>00</resultCode><resultMsg>OK</resultMsg></header><body><items>
<item><year>2026.07</year><statCd>US</statCd><hsCd>8542321010</hsCd><statKor>DRAM</statKor><expDlr>60</expDlr><expWgt>1</expWgt><impDlr>0</impDlr><impWgt>0</impWgt><balPayments>60</balPayments></item>
</items></body></response>'''


def test_parse_and_normalize_itemtrade_drops_total_row():
    rows = parse_customs_xml(ITEM_XML)
    df = normalize_itemtrade(rows)
    assert len(df) == 2
    assert df.loc[0, "hsk10"] == "8542321010"
    assert df.loc[0, "export_usd"] == 100
    assert str(df.loc[0, "date"].date()) == "2026-07-01"


def test_country_and_item_country_normalizers():
    country = normalize_countrytrade(parse_customs_xml(COUNTRY_XML))
    detail = normalize_item_country(parse_customs_xml(ITEM_COUNTRY_XML))
    assert len(country) == 1
    assert country.loc[0, "country_code"] == "US"
    assert detail.loc[0, "hsk10"] == "8542321010"
    assert detail.loc[0, "country_code"] == "US"


def test_aggregate_top20_uses_hsk_mapping_and_preserves_subclassification():
    items = normalize_itemtrade(parse_customs_xml(ITEM_XML))
    mapping = pd.DataFrame([
        {"HSK10": "8542321010", "20대품목": "Semiconductor", "중분류": "Memory", "세부분류": "DRAM", "MTI6": "831110", "HS6": "854232", "HS4": "8542"},
        {"HSK10": "8703231000", "20대품목": "Automobile", "중분류": "Passenger car", "세부분류": "Passenger car", "MTI6": "741100", "HS6": "870323", "HS4": "8703"},
    ])
    out = aggregate_top20(items, mapping)
    assert set(out["item20"]) == {"Semiconductor", "Automobile"}
    assert out.loc[out["item20"] == "Semiconductor", "export_usd"].iloc[0] == 100
    assert out.loc[out["item20"] == "Semiconductor", "mti6"].iloc[0] == "831110"


def test_compute_monthly_metrics_calculates_yoy_and_mom():
    dates = pd.date_range("2025-01-01", periods=14, freq="MS")
    df = pd.DataFrame({"date": dates, "item20": ["Semiconductor"] * 14, "export_usd": list(range(100, 114))})
    out = compute_monthly_metrics(df, ["item20"])
    jan26 = out[out["date"] == pd.Timestamp("2026-01-01")].iloc[0]
    assert round(jan26["yoy_pct"], 6) == round((112 / 100 - 1) * 100, 6)
    assert round(jan26["mom_pct"], 6) == round((112 / 111 - 1) * 100, 6)


def test_latest_safe_customs_month_uses_mid_month_cutoff():
    assert latest_safe_customs_month(date(2026, 9, 11)) == pd.Timestamp("2026-07-01")
    assert latest_safe_customs_month(date(2026, 9, 20)) == pd.Timestamp("2026-08-01")

from customs_pipeline import (
    init_sqlite_db,
    upsert_dataframe,
    save_mapping,
    query_top20_monthly,
    query_top20_country_monthly,
    query_db_status,
)


def test_sqlite_upsert_replaces_same_business_key(tmp_path):
    db = tmp_path / "x.sqlite"
    init_sqlite_db(db)
    first = pd.DataFrame([{ "date": pd.Timestamp("2026-07-01"), "hsk10": "8542321010", "hsk_name": "DRAM", "export_usd": 100, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 100 }])
    second = first.copy(); second.loc[0, "export_usd"] = 120
    upsert_dataframe(db, "raw_item", first, ["date", "hsk10"])
    upsert_dataframe(db, "raw_item", second, ["date", "hsk10"])
    import sqlite3
    with sqlite3.connect(db) as con:
        got = pd.read_sql_query("select * from raw_item", con)
    assert len(got) == 1
    assert got.loc[0, "export_usd"] == 120


def test_query_top20_monthly_and_country_use_mapping(tmp_path):
    db = tmp_path / "x.sqlite"
    init_sqlite_db(db)
    mapping = pd.DataFrame([
        {"HSK10": "8542321010", "20대품목": "Semiconductor", "중분류": "Memory", "세부분류": "DRAM", "MTI6": "831110", "HS6": "854232", "HS4": "8542"}
    ])
    save_mapping(db, mapping)
    items = pd.DataFrame([
        {"date": pd.Timestamp("2025-07-01"), "hsk10": "8542321010", "hsk_name": "DRAM", "export_usd": 100, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 100},
        {"date": pd.Timestamp("2026-07-01"), "hsk10": "8542321010", "hsk_name": "DRAM", "export_usd": 150, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 150},
    ])
    upsert_dataframe(db, "raw_item", items, ["date", "hsk10"])
    ic = pd.DataFrame([
        {"date": pd.Timestamp("2026-07-01"), "country_code": "US", "hsk10": "8542321010", "hsk_name": "DRAM", "export_usd": 60, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 60},
    ])
    upsert_dataframe(db, "raw_item_country", ic, ["date", "country_code", "hsk10"])
    monthly = query_top20_monthly(db)
    july = monthly[monthly["date"] == pd.Timestamp("2026-07-01")].iloc[0]
    assert july["export_usd"] == 150
    assert round(july["yoy_pct"], 6) == 50.0
    c = query_top20_country_monthly(db)
    assert c.iloc[0]["export_usd"] == 60
    assert c.iloc[0]["item20"] == "Semiconductor"

from customs_pipeline import refresh_customs_data


class FakeClient:
    def __init__(self):
        self.calls = []

    def fetch(self, dataset, start, end, country_code=None, hs_code=None):
        self.calls.append((dataset, pd.Timestamp(start), pd.Timestamp(end), country_code, hs_code))
        if dataset == "item":
            return [
                {"year": "2025.07", "hsCode": "8542321010", "statKor": "DRAM", "expDlr": "100", "expWgt": "1", "impDlr": "0", "impWgt": "0", "balPayments": "100"},
                {"year": "2026.07", "hsCode": "8542321010", "statKor": "DRAM", "expDlr": "150", "expWgt": "1", "impDlr": "0", "impWgt": "0", "balPayments": "150"},
            ]
        if dataset == "country":
            return [{"year": "2026.07", "statCd": "US", "statCdCntnKor1": "United States", "expCnt": "1", "expDlr": "500", "impCnt": "1", "impDlr": "400", "balPayments": "100"}]
        if dataset == "item_country":
            return [{"year": "2026.07", "statCd": country_code, "hsCd": "8542321010", "statKor": "DRAM", "expDlr": "60", "expWgt": "1", "impDlr": "0", "impWgt": "0", "balPayments": "60"}]
        raise AssertionError(dataset)


def test_refresh_customs_data_populates_three_datasets_and_mapping(tmp_path):
    db = tmp_path / "x.sqlite"
    mapping = pd.DataFrame([{"HSK10": "8542321010", "20대품목": "Semiconductor", "중분류": "Memory", "세부분류": "DRAM", "MTI6": "831110", "HS6": "854232", "HS4": "8542"}])
    client = FakeClient()
    result = refresh_customs_data(
        client=client,
        db_path=db,
        mapping=mapping,
        target_month=pd.Timestamp("2026-07-01"),
        bootstrap_months=13,
        tracked_countries=["US", "CN"],
        force=True,
    )
    status = query_db_status(db)
    assert status["item_rows"] == 2
    assert status["country_rows"] == 1
    assert status["item_country_rows"] == 2
    assert status["mapping_rows"] == 1
    assert result["target_month"] == "2026-07"
    assert {c[0] for c in client.calls} == {"item", "country", "item_country"}

import customs_pipeline as cp


class ProbeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def fetch(self, dataset, start, end, country_code=None, hs_code=None):
        self.calls.append((dataset, pd.Timestamp(start), pd.Timestamp(end), country_code, hs_code))
        if dataset != "item":
            return []
        return list(self.rows)


def test_probe_latest_item_data_uses_actual_latest_month_returned_by_api():
    client = ProbeClient([
        {"year": "2026.07", "hsCode": "8542321010", "statKor": "DRAM", "expDlr": "100", "expWgt": "1", "impDlr": "0", "impWgt": "0", "balPayments": "100"},
        {"year": "2026.08", "hsCode": "8542321010", "statKor": "DRAM", "expDlr": "120", "expWgt": "1", "impDlr": "0", "impWgt": "0", "balPayments": "120"},
    ])
    result = cp.probe_latest_item_data(client, anchor_month=pd.Timestamp("2026-09-01"), lookback_months=3)
    assert result["latest_month"] == pd.Timestamp("2026-08-01")
    assert set(result["data"]["date"]) == {pd.Timestamp("2026-07-01"), pd.Timestamp("2026-08-01")}
    assert client.calls[0][1] == pd.Timestamp("2026-07-01")
    assert client.calls[0][2] == pd.Timestamp("2026-09-01")


def test_top20_coverage_gate_reports_missing_categories_and_latest_full_month(tmp_path):
    db = tmp_path / "coverage.sqlite"
    init_sqlite_db(db)
    mapping = pd.DataFrame([
        {"HSK10": "0000000001", "20대품목": "A", "중분류": "", "세부분류": "", "MTI6": "100001", "HS6": "000000", "HS4": "0000"},
        {"HSK10": "0000000002", "20대품목": "B", "중분류": "", "세부분류": "", "MTI6": "100002", "HS6": "000000", "HS4": "0000"},
        {"HSK10": "0000000003", "20대품목": "C", "중분류": "", "세부분류": "", "MTI6": "100003", "HS6": "000000", "HS4": "0000"},
    ])
    save_mapping(db, mapping)
    rows = pd.DataFrame([
        {"date": pd.Timestamp("2026-07-01"), "hsk10": "0000000001", "hsk_name": "A", "export_usd": 10, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 10},
        {"date": pd.Timestamp("2026-07-01"), "hsk10": "0000000002", "hsk_name": "B", "export_usd": 20, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 20},
        {"date": pd.Timestamp("2026-07-01"), "hsk10": "0000000003", "hsk_name": "C", "export_usd": 30, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 30},
        {"date": pd.Timestamp("2026-08-01"), "hsk10": "0000000001", "hsk_name": "A", "export_usd": 11, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 11},
        {"date": pd.Timestamp("2026-08-01"), "hsk10": "0000000002", "hsk_name": "B", "export_usd": 21, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 21},
    ])
    upsert_dataframe(db, "raw_item", rows, ["date", "hsk10"])
    gate = cp.query_top20_coverage(db, pd.Timestamp("2026-08-01"))
    assert gate["expected_count"] == 3
    assert gate["observed_count"] == 2
    assert gate["status"] == "FAIL"
    assert gate["missing_items"] == ["C"]
    assert cp.query_latest_full20_month(db) == pd.Timestamp("2026-07-01")


def test_refresh_auto_probe_detects_new_month_and_promotes_it(tmp_path):
    db = tmp_path / "auto.sqlite"
    mapping = pd.DataFrame([
        {"HSK10": "8542321010", "20대품목": "Semiconductor", "중분류": "Memory", "세부분류": "DRAM", "MTI6": "831110", "HS6": "854232", "HS4": "8542"}
    ])
    save_mapping(db, mapping)
    old = pd.DataFrame([{
        "date": pd.Timestamp("2026-07-01"), "hsk10": "8542321010", "hsk_name": "DRAM", "export_usd": 100,
        "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 100,
    }])
    upsert_dataframe(db, "raw_item", old, ["date", "hsk10"])

    class AutoClient(FakeClient):
        def fetch(self, dataset, start, end, country_code=None, hs_code=None):
            self.calls.append((dataset, pd.Timestamp(start), pd.Timestamp(end), country_code, hs_code))
            if dataset == "item":
                return [
                    {"year": "2026.07", "hsCode": "8542321010", "statKor": "DRAM", "expDlr": "105", "expWgt": "1", "impDlr": "0", "impWgt": "0", "balPayments": "105"},
                    {"year": "2026.08", "hsCode": "8542321010", "statKor": "DRAM", "expDlr": "150", "expWgt": "1", "impDlr": "0", "impWgt": "0", "balPayments": "150"},
                ]
            return super().fetch(dataset, start, end, country_code=country_code, hs_code=hs_code)

    client = AutoClient()
    result = refresh_customs_data(
        client=client,
        db_path=db,
        mapping=mapping,
        target_month=None,
        anchor_month=pd.Timestamp("2026-09-01"),
        probe_months=3,
        bootstrap_months=13,
        tracked_countries=[],
        force=False,
    )
    assert result["target_month"] == "2026-08"
    assert result["previous_latest_month"] == "2026-07"
    assert result["new_data_detected"] is True
    assert query_db_status(db)["max_item_date"] == "2026-08-01"


def test_resolve_display_month_promotes_detected_month_only_after_20of20_gate(tmp_path):
    db = tmp_path / "display.sqlite"
    init_sqlite_db(db)
    mapping = pd.DataFrame([
        {"HSK10": "0000000001", "20대품목": "A", "중분류": "", "세부분류": "", "MTI6": "100001", "HS6": "000000", "HS4": "0000"},
        {"HSK10": "0000000002", "20대품목": "B", "중분류": "", "세부분류": "", "MTI6": "100002", "HS6": "000000", "HS4": "0000"},
    ])
    save_mapping(db, mapping)
    rows = pd.DataFrame([
        {"date": pd.Timestamp("2026-07-01"), "hsk10": "0000000001", "hsk_name": "A", "export_usd": 10, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 10},
        {"date": pd.Timestamp("2026-07-01"), "hsk10": "0000000002", "hsk_name": "B", "export_usd": 20, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 20},
        {"date": pd.Timestamp("2026-08-01"), "hsk10": "0000000001", "hsk_name": "A", "export_usd": 11, "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 11},
    ])
    upsert_dataframe(db, "raw_item", rows, ["date", "hsk10"])

    state = cp.resolve_display_month(db, detected_month=pd.Timestamp("2026-08-01"))
    assert state["display_month"] == pd.Timestamp("2026-07-01")
    assert state["detected_month"] == pd.Timestamp("2026-08-01")
    assert state["detected_coverage"]["status"] == "FAIL"
    assert state["using_detected_month"] is False

    missing = pd.DataFrame([{
        "date": pd.Timestamp("2026-08-01"), "hsk10": "0000000002", "hsk_name": "B", "export_usd": 21,
        "export_weight": 1, "import_usd": 0, "import_weight": 0, "balance_usd": 21,
    }])
    upsert_dataframe(db, "raw_item", missing, ["date", "hsk10"])
    state2 = cp.resolve_display_month(db, detected_month=pd.Timestamp("2026-08-01"))
    assert state2["display_month"] == pd.Timestamp("2026-08-01")
    assert state2["detected_coverage"]["status"] == "PASS"
    assert state2["using_detected_month"] is True


def test_real_mapping_has_exactly_20_categories_and_unique_hsk():
    from pathlib import Path
    mapping_path = Path(__file__).resolve().parents[1] / "data" / "motir20_hsk_mti_mapping_2026.csv"
    m = pd.read_csv(mapping_path, dtype=str)
    sm = cp.standardize_mapping(m)
    assert sm["item20"].nunique() == 20
    assert sm["hsk10"].is_unique
    assert len(sm) >= 8000


def test_parse_customs_xml_raises_gateway_auth_error_message():
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <OpenAPI_ServiceResponse><cmmMsgHeader>
      <errMsg>SERVICE KEY IS NOT REGISTERED ERROR.</errMsg>
      <returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
      <returnReasonCode>30</returnReasonCode>
    </cmmMsgHeader></OpenAPI_ServiceResponse>'''
    import pytest
    with pytest.raises(RuntimeError, match="SERVICE KEY IS NOT REGISTERED"):
        parse_customs_xml(xml)


def test_parse_customs_xml_raises_useful_error_for_non_xml_gateway_response():
    import pytest
    with pytest.raises(RuntimeError, match="non-XML"):
        parse_customs_xml(b"Bad Gateway")
