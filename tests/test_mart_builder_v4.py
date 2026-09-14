from pathlib import Path
import sqlite3

import pandas as pd

from customs_pipeline import init_sqlite_db, upsert_dataframe
from mart_builder import _trade_metrics, build_analysis_mart, mart_status


def test_trade_metrics_do_not_treat_twelfth_sparse_observation_as_prior_year():
    dates = list(pd.date_range("2010-01-01", "2010-12-01", freq="MS")) + [pd.Timestamp("2024-01-01")]
    sparse = pd.DataFrame({
        "date": dates,
        "product": ["무선통신기기 부품"] * len(dates),
        "export_usd": [100.0] * 12 + [10_000.0],
    })

    out = _trade_metrics(sparse, ["product"])
    jan_2024 = out[out["date"] == pd.Timestamp("2024-01-01")].iloc[0]
    feb_2011 = out[out["date"] == pd.Timestamp("2011-02-01")].iloc[0]

    assert pd.isna(jan_2024["yoy_pct"])
    assert pd.isna(feb_2011["export_usd"])


def test_trade_metrics_leave_growth_blank_when_comparison_amount_is_zero():
    frame = pd.DataFrame({
        "date": [pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01")],
        "product": ["A", "A"],
        "export_usd": [0.0, 100.0],
    })
    out = _trade_metrics(frame, ["product"])
    yoy = out.loc[out["date"] == pd.Timestamp("2024-01-01"), "yoy_pct"].iloc[0]
    assert pd.isna(yoy)


def _fixture_taxonomy(path: Path):
    pd.DataFrame([
        {"20대품목":"컴퓨터","리서치중분류":"서버","대표품목명":"AI 서버","대표품목ID":"PC_SERVER","드릴다운명":"AI 서버용 부품","드릴다운ID":"D1","분류상태":"검토","분류메모":"","MTI6":"813100","HSK10":"1111111111","HS6":"111111","HS4":"1111","HSK 품목명":"품목1","리서치대분류":"ICT","리서치소분류":"서버","리서치세분류":"AI 서버"},
        {"20대품목":"반도체","리서치중분류":"메모리반도체","대표품목명":"DRAM","대표품목ID":"SEMI_DRAM","드릴다운명":"DRAM","드릴다운ID":"D2","분류상태":"검토","분류메모":"","MTI6":"831110","HSK10":"2222222222","HS6":"222222","HS4":"2222","HSK 품목명":"품목2","리서치대분류":"반도체","리서치소분류":"DRAM","리서치세분류":"DRAM"},
    ]).to_csv(path, index=False, encoding="utf-8-sig")


def _fixture_raw_db(path: Path):
    init_sqlite_db(path)
    rows = []
    for month in pd.date_range("2024-01-01", "2025-12-01", freq="MS"):
        i = (month.year - 2024) * 12 + month.month
        rows += [
            {"date":month,"hsk10":"1111111111","hsk_name":"품목1","export_usd":100+i*10,"export_weight":10+i,"import_usd":30,"import_weight":3,"balance_usd":70+i*10},
            {"date":month,"hsk10":"2222222222","hsk_name":"품목2","export_usd":200+i*5,"export_weight":20+i,"import_usd":40,"import_weight":4,"balance_usd":160+i*5},
        ]
    upsert_dataframe(path, "raw_item", pd.DataFrame(rows), ["date","hsk10"])
    country = pd.DataFrame([
        {"date":pd.Timestamp("2025-12-01"),"country_code":"US","hsk10":"1111111111","hsk_name":"품목1","export_usd":1000,"export_weight":20,"import_usd":0,"import_weight":0,"balance_usd":1000},
        {"date":pd.Timestamp("2025-12-01"),"country_code":"CN","hsk10":"1111111111","hsk_name":"품목1","export_usd":500,"export_weight":25,"import_usd":0,"import_weight":0,"balance_usd":500},
    ])
    upsert_dataframe(path, "raw_item_country", country, ["date","country_code","hsk10"])


def _fixture_kosis(path: Path):
    rows=[]
    for month in pd.date_range("2024-01-01","2025-12-01",freq="MS"):
        prd=month.strftime("%Y%m")
        for item, value in [("생산지수(계절조정)",100+month.month),("생산자제품 출하지수(계절조정)",105+month.month),("생산자제품 재고지수(계절조정)",98+month.month)]:
            rows.append({"PRD_DE":prd,"IND_CODE":"C26","ITM_NM":item,"DT_val":value})
    pd.DataFrame(rows).to_csv(path,index=False)


def _fixture_bridge(path: Path):
    pd.DataFrame([
        {"ksic_code":"C26","ksic_name":"전자부품·컴퓨터·영상·통신","export_item":"컴퓨터","weight":1.0,"mapping_quality":"중간","note":""},
    ]).to_csv(path,index=False)


def test_build_analysis_mart_creates_compact_hierarchy_and_country(tmp_path):
    raw=tmp_path/"raw.sqlite"; mart=tmp_path/"mart.sqlite"; tax=tmp_path/"tax.csv"; kosis=tmp_path/"kosis.csv"; bridge=tmp_path/"bridge.csv"
    _fixture_raw_db(raw); _fixture_taxonomy(tax); _fixture_kosis(kosis); _fixture_bridge(bridge)
    result=build_analysis_mart(raw, mart, tax, kosis, bridge)
    assert result["top20_rows"] == 48
    with sqlite3.connect(mart) as con:
        top20=pd.read_sql_query("select * from mart_export_top20_monthly", con)
        middle=pd.read_sql_query("select * from mart_export_middle_monthly", con)
        product=pd.read_sql_query("select * from mart_export_product_monthly", con)
        country=pd.read_sql_query("select * from mart_product_country_monthly", con)
        dim=pd.read_sql_query("select * from dim_product_taxonomy", con)
    assert set(top20["item20"]) == {"컴퓨터","반도체"}
    assert set(middle["middle_category"]) == {"서버","메모리반도체"}
    assert set(product["product"]) == {"AI 서버","DRAM"}
    assert set(country["country_code"]) == {"US","CN"}
    assert dim["hsk10"].nunique() == 2
    assert "yoy_pct" in product.columns


def test_industry_signal_and_status_are_created(tmp_path):
    raw=tmp_path/"raw.sqlite"; mart=tmp_path/"mart.sqlite"; tax=tmp_path/"tax.csv"; kosis=tmp_path/"kosis.csv"; bridge=tmp_path/"bridge.csv"
    _fixture_raw_db(raw); _fixture_taxonomy(tax); _fixture_kosis(kosis); _fixture_bridge(bridge)
    build_analysis_mart(raw, mart, tax, kosis, bridge)
    status=mart_status(mart)
    assert status["ready"] is True
    assert status["latest_export_month"] == "2025-12"
    with sqlite3.connect(mart) as con:
        sig=pd.read_sql_query("select * from mart_industry_signal_monthly", con)
    assert "industry_score" in sig.columns
    assert (sig["item20"] == "컴퓨터").any()


def test_build_analysis_mart_works_without_kosis_cache(tmp_path):
    raw=tmp_path/'raw.sqlite'; mart=tmp_path/'mart.sqlite'; tax=tmp_path/'tax.csv'; bridge=tmp_path/'bridge.csv'
    _fixture_raw_db(raw); _fixture_taxonomy(tax); _fixture_bridge(bridge)
    result=build_analysis_mart(raw,mart,tax,tmp_path/'missing.csv',bridge)
    assert result['cycle_rows'] == 0
    assert mart_status(mart)['ready'] is True
    with sqlite3.connect(mart) as con:
        assert con.execute("SELECT COUNT(*) FROM mart_kosis_cycle_monthly").fetchone()[0] == 0


def test_fundamental_score_rewards_broad_persistent_improvement_over_one_month_spike():
    from mart_builder import score_industry_fundamentals

    months = pd.date_range("2025-01-01", "2025-06-01", freq="MS")
    rows = []
    # '기저효과' has an eye-catching latest export YoY, but weak real activity,
    # negative inventory cycle, weak breadth, and no persistence.
    spike_export = [-18, -15, -12, -8, -4, 80]
    # '광범위개선' improves steadily across exports and KOSIS signals.
    broad_export = [5, 7, 9, 11, 13, 15]
    for i, month in enumerate(months):
        rows.extend([
            {
                "date": month, "item20": "기저효과", "export_usd": 100,
                "export_yoy": spike_export[i], "export_mom": 0,
                "production_yoy": -5, "shipment_yoy": -4,
                "inventory_yoy": 6, "inventory_cycle": -10,
            },
            {
                "date": month, "item20": "광범위개선", "export_usd": 100,
                "export_yoy": broad_export[i], "export_mom": 0,
                "production_yoy": 8 + i * 0.4, "shipment_yoy": 9 + i * 0.5,
                "inventory_yoy": 2, "inventory_cycle": 7 + i * 0.5,
            },
        ])

    middle_rows = []
    for month in months:
        # spike: only one of four sub-industries is positive
        for name, yoy in [("A", 70), ("B", -15), ("C", -20), ("D", -5)]:
            middle_rows.append({"date": month, "item20": "기저효과", "middle_category": name, "yoy_pct": yoy})
        # broad: four of five sub-industries positive
        for name, yoy in [("A", 12), ("B", 8), ("C", 15), ("D", 5), ("E", -2)]:
            middle_rows.append({"date": month, "item20": "광범위개선", "middle_category": name, "yoy_pct": yoy})

    scored = score_industry_fundamentals(pd.DataFrame(rows), pd.DataFrame(middle_rows))
    latest = scored[scored["date"] == months[-1]].set_index("item20")

    required = {
        "fundamental_score", "export_momentum_score", "inventory_cycle_score",
        "real_activity_score", "breadth_score", "persistence_score",
        "breadth_pct", "persistence_pct", "score_note",
    }
    assert required.issubset(scored.columns)
    assert latest.loc["광범위개선", "fundamental_score"] > latest.loc["기저효과", "fundamental_score"]
    assert latest.loc["광범위개선", "breadth_pct"] == 80.0
    assert latest.loc["기저효과", "breadth_pct"] == 25.0


def test_fundamental_score_caps_jointly_negative_export_and_inventory_cycle():
    from mart_builder import score_industry_fundamentals

    months = pd.date_range("2025-01-01", "2025-06-01", freq="MS")
    signal = pd.DataFrame([
        {
            "date": month, "item20": "약한산업", "export_usd": 100,
            "export_yoy": -2, "export_mom": 0,
            "production_yoy": 20, "shipment_yoy": 20,
            "inventory_yoy": 21, "inventory_cycle": -1,
        }
        for month in months
    ])
    middle = pd.DataFrame([
        {"date": month, "item20": "약한산업", "middle_category": f"M{i}", "yoy_pct": 20}
        for month in months for i in range(5)
    ])
    scored = score_industry_fundamentals(signal, middle)
    latest = scored.iloc[-1]
    assert latest["fundamental_score"] <= 50.0
    assert "수출·재고순환 동반 약세" in latest["score_note"]
