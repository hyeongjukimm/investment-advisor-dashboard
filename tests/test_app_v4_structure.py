from pathlib import Path


def test_v4_app_is_mart_first_and_has_phase1_pages():
    text=Path("app.py").read_text(encoding="utf-8")
    assert "Investment Advisor Tool · v4" in text
    for page in ["종합 현황","산업 스크리너","산업 상세","수출 성장","품목 모니터","최근 수출","데이터 점검"]:
        assert page in text
    assert "resolve_mart_path" in text
    assert "mart_export_top20_monthly" in text
    assert "Top20 → 리서치중분류 → 대표품목" in text


def test_chart_download_is_one_compact_action_not_monkey_patch():
    text=Path("app.py").read_text(encoding="utf-8")
    assert "def render_chart(" in text
    assert '"CSV"' in text
    assert "st.plotly_chart =" not in text


def test_cross_platform_and_portable_scripts_exist():
    for name in ["START_MAC.command","START_WINDOWS.bat","MIGRATE_FROM_V3_2.command","MIGRATE_FROM_V3_2.bat","BUILD_MARTS.command","BUILD_MARTS.bat","MAKE_PORTABLE.command","MAKE_PORTABLE.bat"]:
        assert Path(name).exists(), name


def test_distribution_has_no_real_secrets_file():
    assert not Path('.streamlit/secrets.toml').exists()
    assert Path('.streamlit/secrets.toml.example').exists()


def test_v41_uses_fundamental_score_language_and_components():
    text = Path("app.py").read_text(encoding="utf-8")
    assert "Fundamental Score" in text
    assert "breadth_score" in text
    assert "persistence_score" in text
    assert "주가·EPS·수급은 아직 포함하지 않습니다" in text
