import sqlite3
from pathlib import Path

import pytest

import scheduled_refresh


def test_refresh_requires_existing_raw_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        scheduled_refresh.run_refresh(tmp_path, environ={})


def test_refresh_without_keys_builds_and_promotes_existing_data(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    (data / "investment_advisor.sqlite").write_bytes(b"raw")
    calls = []

    def fake_build(raw, mart, taxonomy, kosis, bridge):
        calls.append((Path(raw), Path(mart)))
        Path(mart).write_bytes(b"mart")
        return {"top20_rows": 3}

    def fake_share(mart, share):
        Path(share).write_bytes(b"share")
        return Path(share)

    monkeypatch.setattr(scheduled_refresh, "build_analysis_mart", fake_build)
    monkeypatch.setattr(scheduled_refresh, "make_share_snapshot", fake_share)
    monkeypatch.setattr(scheduled_refresh, "refresh_flash_cache", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(scheduled_refresh, "promote_snapshot", lambda c, t: Path(t).write_bytes(Path(c).read_bytes()) or {"rows": 3})
    result = scheduled_refresh.run_refresh(tmp_path, environ={})
    assert result["ok"] is True
    assert result["kosis"] == "기존 캐시 사용"
    assert result["customs"] == "기존 DB 사용"
    assert (data / "share_snapshot.sqlite").read_bytes() == b"share"


def test_refresh_failure_does_not_replace_last_good_snapshot(tmp_path, monkeypatch):
    data = tmp_path / "data"; data.mkdir()
    (data / "investment_advisor.sqlite").write_bytes(b"raw")
    target = data / "share_snapshot.sqlite"; target.write_bytes(b"last-good")
    monkeypatch.setattr(scheduled_refresh, "refresh_flash_cache", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(scheduled_refresh, "build_analysis_mart", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("build failed")))
    with pytest.raises(RuntimeError):
        scheduled_refresh.run_refresh(tmp_path, environ={})
    assert target.read_bytes() == b"last-good"
