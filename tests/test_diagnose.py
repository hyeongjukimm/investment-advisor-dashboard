from pathlib import Path
import pytest


def test_load_project_secrets_reads_both_keys(tmp_path):
    from diagnose import load_project_secrets
    d = tmp_path / '.streamlit'
    d.mkdir()
    (d / 'secrets.toml').write_text(
        'KOSIS_API_KEY="abc"\nCUSTOMS_SERVICE_KEY="xyz%2B123"\n',
        encoding='utf-8',
    )
    cfg = load_project_secrets(tmp_path)
    assert cfg['KOSIS_API_KEY'] == 'abc'
    assert cfg['CUSTOMS_SERVICE_KEY'] == 'xyz%2B123'


def test_load_project_secrets_fails_clearly_when_missing(tmp_path):
    from diagnose import load_project_secrets
    with pytest.raises(FileNotFoundError, match='secrets.toml'):
        load_project_secrets(tmp_path)
