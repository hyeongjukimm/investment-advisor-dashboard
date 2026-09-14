from pathlib import Path


def test_refresh_workflow_has_schedule_manual_trigger_secrets_and_validation():
    text = Path(".github/workflows/refresh-data.yml").read_text(encoding="utf-8")
    for token in ["schedule:", "cron: '30 23 * * *'", "workflow_dispatch:",
                  "KOSIS_API_KEY", "CUSTOMS_SERVICE_KEY", "scheduled_refresh.py",
                  "validate_snapshot.py", "concurrency:", "raw-state.zip"]:
        assert token in text


def test_gitignore_excludes_raw_db_but_allows_share_snapshot():
    text = Path(".gitignore").read_text(encoding="utf-8")
    assert "data/investment_advisor.sqlite" in text
    assert "!data/share_snapshot.sqlite" in text
    assert ".streamlit/secrets.toml" in text


def test_streamlit_is_headless_and_has_no_real_secrets():
    config = Path(".streamlit/config.toml").read_text(encoding="utf-8")
    assert "headless = true" in config
    assert not Path(".streamlit/secrets.toml").exists()
