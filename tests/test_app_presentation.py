import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
TEXT = APP.read_text(encoding="utf-8")


def test_v4_is_mart_first_and_lazy_pages():
    assert "Investment Advisor Tool · v4" in TEXT
    assert "resolve_mart_path" in TEXT
    assert "st.tabs(" not in TEXT
    assert "page = st.radio(" in TEXT


def test_v4_has_calendar_controls_and_quick_ranges():
    assert 'text_input("기간 시작"' in TEXT
    assert 'text_input("기간 종료"' in TEXT
    assert "parse_date_text" in TEXT
    assert '"1Y", "3Y", "5Y", "10Y", "전체"' in TEXT
    assert "normalize_month_range" in TEXT


def test_growth_mode_defaults_to_previous_equal_period_and_explains_comparison():
    preferred = "선택기간 합계 vs 직전 동일기간 합계"
    alternative = "초반 3개월 평균 vs 최근 3개월 평균"
    assert TEXT.index(preferred) < TEXT.index(alternative)
    assert "현재 비교:" in TEXT


def test_quick_range_always_controls_dates_until_direct_mode_is_selected():
    assert 'if quick != "직접":' in TEXT
    assert 'st.session_state.get("_quick_last")' not in TEXT
    assert 'st.session_state["_quick_last"]' not in TEXT


def test_navigation_and_flash_page_use_korean_labels_and_canonical_schema():
    for label in ["종합 현황", "산업 스크리너", "산업 상세", "수출 성장", "품목 모니터", "종목 후보", "최근 수출", "데이터 점검"]:
        assert label in TEXT
    assert 'current["checkpoint_day"]' in TEXT
    assert 'latest["export_usd_m"]' in TEXT
    assert 'current["checkpoint_days"]' not in TEXT


def test_v4_has_explicit_local_refresh_only():
    assert "관세청 + Mart 최신화" in TEXT
    assert "KOSIS + Mart 최신화" in TEXT
    assert "실행 시 관세청 최신화" not in TEXT


def test_v4_trade_units_are_100m_usd():
    assert "억달러" in TEXT
    assert "format_100m_usd" in TEXT


def test_v4_download_helper_is_not_monkey_patch():
    assert "def render_chart(" in TEXT
    assert "st.plotly_chart =" not in TEXT


def test_every_chart_declares_its_data_source():
    tree = ast.parse(TEXT)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "render_chart"
    ]
    assert calls
    missing = [node.lineno for node in calls if not any(kw.arg == "source_key" for kw in node.keywords)]
    assert missing == [], f"render_chart calls missing source_key at lines {missing}"
