import numpy as np
import pandas as pd

from export_analytics import prepare_chartbook_series, growth_leaders, cycle_polynomial_curve, mapping_waterfall


def test_prepare_chartbook_series_builds_yoy_mom_ytd_and_prior_ytd():
    dates = pd.date_range("2025-01-01", periods=14, freq="MS")
    df = pd.DataFrame({"date": dates, "item20": ["반도체"] * 14, "export_usd": np.arange(100, 114, dtype=float)})
    out = prepare_chartbook_series(df, "item20", "반도체")
    jan26 = out[out["date"] == pd.Timestamp("2026-01-01")].iloc[0]
    assert round(jan26["yoy_pct"], 6) == round((112 / 100 - 1) * 100, 6)
    assert round(jan26["mom_pct"], 6) == round((112 / 111 - 1) * 100, 6)
    assert jan26["ytd_usd"] == 112
    assert jan26["prior_year_ytd_usd"] == 100
    assert round(jan26["ytd_yoy_pct"], 6) == 12.0


def test_growth_leaders_endpoint_mode_ranks_by_three_month_run_rate_growth():
    dates = pd.date_range("2025-01-01", periods=6, freq="MS")
    rows = []
    for d, a, b in zip(dates, [100,100,100,150,150,150], [100,100,100,110,110,110]):
        rows += [{"date": d, "item20": "A", "export_usd": a}, {"date": d, "item20": "B", "export_usd": b}]
    out = growth_leaders(pd.DataFrame(rows), "item20", dates[0], dates[-1], min_base_usd=0, mode="endpoint")
    assert out.iloc[0]["entity"] == "A"
    assert round(out.iloc[0]["growth_pct"], 1) == 50.0
    assert round(out["contribution_pct"].sum(), 6) == 100.0


def test_cycle_polynomial_curve_returns_smooth_curve_and_latest_point():
    x = np.array([-3,-2,-1,0,1,2,3], dtype=float)
    y = x**2 + 2*x + 1
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=len(x), freq="MS"), "inventory_cycle": x, "shipment_yoy": y})
    curve, latest = cycle_polynomial_curve(df, "inventory_cycle", "shipment_yoy", order=2, points=25)
    assert len(curve) == 25
    assert abs(curve.iloc[0]["y_fit"] - (curve.iloc[0]["x_fit"] + 1) ** 2) < 1e-6
    assert latest["inventory_cycle"] == 3


def test_mapping_waterfall_has_total_mapped_and_gap_steps():
    row = {"total_export_usd": 100, "mapped_export_usd": 82, "unmapped_export_usd": 18}
    out = mapping_waterfall(row)
    assert out["step"].tolist() == ["HS10 전체", "Top20 매핑", "미매핑 Gap"]
    assert out["value_usd"].tolist() == [100, 82, 18]

def test_growth_leaders_uses_pre_period_history_for_latest_yoy():
    dates = pd.date_range("2025-01-01", periods=20, freq="MS")
    df = pd.DataFrame({"date": dates, "item20": ["A"]*20, "export_usd": [100.0]*12 + [120.0]*8})
    out = growth_leaders(df, "item20", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-08-01"), min_base_usd=0, mode="endpoint")
    assert round(out.iloc[0]["latest_yoy_pct"], 1) == 20.0
    assert round(out.iloc[0]["avg_yoy_pct"], 1) == 20.0
