from pathlib import Path

import scheduled_refresh as sr
from kosis_client import KosisApiError


def test_scheduled_refresh_keeps_cache_on_kosis_error_object(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "investment_advisor.sqlite").touch()

    monkeypatch.setattr(
        sr,
        "fetch_kosis_history_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            KosisApiError("KOSIS object response", err="10", err_msg="인증 실패")
        ),
    )
    monkeypatch.setattr(sr, "refresh_flash_cache", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(sr, "build_analysis_mart", lambda *args, **kwargs: {"top20_rows": 1})
    monkeypatch.setattr(sr, "make_share_snapshot", lambda *args, **kwargs: Path(args[1]).touch())
    monkeypatch.setattr(sr, "promote_snapshot", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(sr.os, "replace", lambda *args, **kwargs: None)
    monkeypatch.setattr(sr, "_write_status", lambda *args, **kwargs: None)

    result = sr.run_refresh(tmp_path, environ={"KOSIS_API_KEY": "x", "NETWORK_RETRY_ATTEMPTS": "1"})

    assert result["ok"] is True
    assert "기존 캐시 유지" in result["kosis"]
    assert any("KosisApiError" in warning and "인증 실패" in warning for warning in result["warnings"])
