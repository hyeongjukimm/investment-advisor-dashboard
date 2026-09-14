import pandas as pd

from dashboard_utils import (
    normalize_month_range,
    quick_month_range,
    filter_month_range,
    usd_to_100m,
    format_100m_usd,
    industry_period_summary,
    sidebar_guide_sections,
)


def test_normalize_month_range_orders_and_month_normalizes():
    start, end = normalize_month_range("2026-08-28", "2025-01-15")
    assert start == pd.Timestamp("2025-01-01")
    assert end == pd.Timestamp("2026-08-01")


def test_quick_month_range_three_years_is_36_months_inclusive():
    start, end = quick_month_range(pd.Timestamp("2026-08-01"), "3Y", pd.Timestamp("1995-01-01"))
    assert end == pd.Timestamp("2026-08-01")
    assert start == pd.Timestamp("2023-09-01")


def test_quick_month_range_all_uses_available_start():
    start, end = quick_month_range(pd.Timestamp("2026-08-01"), "전체", pd.Timestamp("1995-01-01"))
    assert start == pd.Timestamp("1995-01-01")
    assert end == pd.Timestamp("2026-08-01")


def test_filter_month_range_keeps_only_selected_months():
    df = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=6, freq="MS"), "x": range(6)})
    out = filter_month_range(df, "2025-03-15", "2025-05-20")
    assert out["date"].tolist() == [pd.Timestamp("2025-03-01"), pd.Timestamp("2025-04-01"), pd.Timestamp("2025-05-01")]


def test_usd_to_100m_and_formatter():
    assert usd_to_100m(2_350_000_000) == 23.5
    assert format_100m_usd(2_350_000_000) == "23.5억달러"
    assert format_100m_usd(None) == "-"


def test_industry_period_summary_uses_selected_start_and_end():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-03-01", "2026-01-01", "2026-03-01"]),
        "item20": ["A", "A", "B", "B"],
        "fundamental_score": [40.0, 70.0, 80.0, 60.0],
    })
    out = industry_period_summary(df)
    a = out[out["item20"] == "A"].iloc[0]
    assert a["period_avg_score"] == 55.0
    assert a["period_change_score"] == 30.0
    assert a["fundamental_score"] == 70.0


def test_sidebar_guide_explains_navigation_mapping_and_updates():
    sections = sidebar_guide_sections()

    assert list(sections) == [
        "처음 보는 분을 위한 빠른 시작",
        "종합 현황",
        "산업 스크리너",
        "산업 상세",
        "수출 성장",
        "품목 모니터",
        "종목 후보",
        "최근 수출",
        "지표·점수 해석",
        "분류·매핑 확인",
        "데이터 갱신·웹 반영",
        "데이터 한계와 주의사항",
    ]
    assert "HS10 → 리서치 중분류 → 대표품목 → 산업부 Top20" in sections["분류·매핑 확인"]
    assert "데이터 점검" in sections["분류·매핑 확인"]
    assert "Commit to main → Push origin" in sections["데이터 갱신·웹 반영"]
