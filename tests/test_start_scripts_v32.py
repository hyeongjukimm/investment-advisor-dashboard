from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mac_start_uses_requirement_marker_for_fast_restarts():
    text=(ROOT/"START_MAC.command").read_text(encoding="utf-8")
    assert ".requirements_v4" in text
    assert "streamlit run app.py" in text


def test_windows_start_opens_dashboard_on_loopback():
    text = (ROOT / "START_WINDOWS.bat").read_text(encoding="utf-8")
    assert 'start "" http://127.0.0.1:8501' in text
    assert "--server.address 127.0.0.1" in text


def test_v4_migration_script_exists_and_copies_sqlite():
    p=ROOT/"MIGRATE_FROM_V3_2.command"
    assert p.exists()
    text=p.read_text(encoding="utf-8")
    assert "investment_advisor_READY_v3.2" in text
    assert "investment_advisor.sqlite" in text
    assert "build_marts.py" in text


def test_readme_mentions_mart_first_and_portable():
    text=(ROOT/"README.md").read_text(encoding="utf-8")
    assert "READY v4" in text
    assert "Mart-first" in text
    assert "MAKE_PORTABLE" in text


def test_v41_has_v4_migration_and_company_zip_scripts():
    root = Path(".")
    for name in ["MIGRATE_FROM_V4.command", "MIGRATE_FROM_V4.bat", "MAKE_COMPANY_ZIP.command", "MAKE_COMPANY_ZIP.bat"]:
        assert (root / name).exists(), name
    portable = (root / "make_portable.py").read_text(encoding="utf-8")
    assert "v4.1" in portable
    assert "share_snapshot.sqlite" in portable
