import pandas as pd

from flash_trade import parse_customs_homepage_flash, flash_comparison_frame, normalize_flash_schema


def test_parse_customs_homepage_flash_extracts_period_and_totals():
    text = """
    이달의 통관실적 수리일 기준(백만불, %(전년동기대비))
    당월(9.1 - 9. 10) 수출 34,973 82.6 수입 24,606 20.7
    연간(1.1-9.10) 수출 728,561 54.1 수입 515,570 18.9
    조업 일수[(’25) 8.5일, (’26) 8.5일]
    """
    row = parse_customs_homepage_flash(text, year=2026)
    assert row["month"] == "2026-09"
    assert row["checkpoint_day"] == 10
    assert row["export_usd_m"] == 34973
    assert row["import_usd_m"] == 24606
    assert row["export_yoy_pct"] == 82.6


def test_flash_comparison_frame_marks_current_prior_year_and_prior_month():
    df = pd.DataFrame([
        {"month":"2025-09", "checkpoint_day":10, "export_usd_m":19154, "import_usd_m":20383, "export_yoy_pct":3.7},
        {"month":"2026-08", "checkpoint_day":10, "export_usd_m":21286, "import_usd_m":19488, "export_yoy_pct":45.3},
        {"month":"2026-09", "checkpoint_day":10, "export_usd_m":34973, "import_usd_m":24606, "export_yoy_pct":82.6},
    ])
    out = flash_comparison_frame(df, "2026-09", 10)
    assert set(out["comparison"]) == {"현재", "전년동기", "전월동일구간"}
    assert out.loc[out["comparison"] == "현재", "export_usd_m"].iloc[0] == 34973

def test_parse_customs_homepage_flash_handles_html_tags():
    html = '''<div>이달의 통관실적</div><li>당월(9.1 - 9. 10)</li><span>수출</span><b>34,973</b><em>82.6</em><span>수입</span><b>24,606</b><em>20.7</em>'''
    row = parse_customs_homepage_flash(html, year=2026)
    assert row["export_usd_m"] == 34973
    assert row["checkpoint_day"] == 10


def test_normalize_flash_schema_accepts_legacy_plural_and_app_names():
    legacy = pd.DataFrame([{
        "month": "2026-09", "checkpoint_days": 10,
        "export_usd": 34973000000, "yoy_pct": 82.6,
    }])
    out = normalize_flash_schema(legacy)
    assert out.loc[0, "checkpoint_day"] == 10
    assert out.loc[0, "export_usd_m"] == 34973
    assert out.loc[0, "export_yoy_pct"] == 82.6


def test_normalize_flash_schema_coalesces_legacy_values_when_canonical_is_blank():
    mixed = pd.DataFrame([{
        "month": "2026-09", "checkpoint_day": pd.NA, "checkpoint_days": 20,
        "export_yoy_pct": pd.NA, "yoy_pct": 12.3,
    }])
    out = normalize_flash_schema(mixed)
    assert out.loc[0, "checkpoint_day"] == 20
    assert out.loc[0, "export_yoy_pct"] == 12.3
