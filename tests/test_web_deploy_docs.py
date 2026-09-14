from pathlib import Path


def test_windows_prepare_script_builds_validates_and_archives_state():
    text = Path("PREPARE_WEB_DEPLOY.bat").read_text(encoding="utf-8")
    for token in ["build_marts.py", "make_share_snapshot", "validate_snapshot.py", "raw-state.zip", "investment_advisor.sqlite"]:
        assert token in text
    assert "secrets.toml" not in text


def test_korean_manual_covers_three_user_actions_and_security():
    text = Path("README_WEB_DEPLOY.md").read_text(encoding="utf-8")
    for token in ["GitHub Desktop", "data-state", "KOSIS_API_KEY", "CUSTOMS_SERVICE_KEY", "Streamlit Community Cloud", "share_snapshot.sqlite"]:
        assert token in text
    assert "secrets.toml을 업로드" not in text
