from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from customs_pipeline import CustomsClient, refresh_customs_data
from flash_trade import refresh_flash_cache
from kosis_cache import write_kosis_cache
from kosis_client import KosisApiError, fetch_kosis_history_payload
from mart_builder import build_analysis_mart, make_share_snapshot
from validate_snapshot import promote_snapshot


def _normalize_kosis(payload) -> pd.DataFrame:
    df = pd.DataFrame(payload)
    if df.empty:
        return df
    code_col = next((c for c in ["C2", "C1", "C2_NM", "C1_NM"] if c in df.columns), None)
    if code_col is None or not {"DT", "PRD_DE"}.issubset(df.columns):
        raise ValueError(f"예상하지 못한 KOSIS 스키마: {list(df.columns)}")
    df["IND_CODE"] = df[code_col].astype(str).str.strip()
    df["DT_val"] = pd.to_numeric(df["DT"].astype(str).str.replace(",", "", regex=False), errors="coerce")
    df["PRD_DE"] = df["PRD_DE"].astype(str)
    return df.dropna(subset=["PRD_DE", "DT_val", "IND_CODE"])


def _write_status(path: Path, result: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _retry_network(operation, *, attempts: int, delay_seconds: float = 2.0):
    attempts = max(1, attempts)
    for attempt in range(attempts):
        try:
            return operation()
        except requests.RequestException:
            if attempt + 1 >= attempts:
                raise
            time.sleep(delay_seconds * (attempt + 1))


def run_refresh(base_dir: str | Path, *, environ=None) -> dict:
    root = Path(base_dir).resolve(); data = root / "data"
    env = os.environ if environ is None else environ
    raw = data / "investment_advisor.sqlite"
    if not raw.is_file():
        raise FileNotFoundError(f"원본 DB가 없습니다: {raw}")

    result = {
        "ok": False,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kosis": "기존 캐시 사용",
        "customs": "기존 DB 사용",
        "warnings": [],
    }
    kosis_key = str(env.get("KOSIS_API_KEY", "") or "").strip()
    customs_key = str(env.get("CUSTOMS_SERVICE_KEY", "") or "").strip()
    retry_attempts = int(env.get("NETWORK_RETRY_ATTEMPTS", "3") or 3)

    if kosis_key:
        try:
            payload, _ = _retry_network(
                lambda: fetch_kosis_history_payload(
                    kosis_key,
                    months=int(env.get("KOSIS_HISTORY_MONTHS", "600") or 600),
                    chunk_months=12,
                    verify_ssl=str(env.get("KOSIS_VERIFY_SSL", "false")).lower() not in {"0", "false", "no"},
                ),
                attempts=retry_attempts,
            )
            frame = _normalize_kosis(payload)
            if not frame.empty:
                write_kosis_cache(frame, data / "kosis_cycle_cache.csv")
                result["kosis"] = f"{len(frame):,}행 갱신"
        except (requests.RequestException, KosisApiError) as exc:
            error_name = type(exc).__name__
            result["kosis"] = f"기존 캐시 유지 ({error_name})"
            detail = str(exc).strip()
            api_detail = str(getattr(exc, "err_msg", "") or "").strip()
            if api_detail and api_detail not in detail:
                detail = f"{detail} · {api_detail}" if detail else api_detail
            result["warnings"].append(
                f"KOSIS 갱신 오류: {error_name}" + (f" · {detail}" if detail else "")
            )

    if customs_key:
        mapping = pd.read_csv(data / "motir20_hsk_mti_mapping_2026.csv", dtype=str).fillna("")
        try:
            update = _retry_network(
                lambda: refresh_customs_data(
                    client=CustomsClient(customs_key, verify_ssl=False, timeout=90),
                    db_path=raw,
                    mapping=mapping,
                    target_month=None,
                    bootstrap_months=int(env.get("CUSTOMS_BOOTSTRAP_MONTHS", "24") or 24),
                    tracked_countries=[x.strip().upper() for x in str(env.get("CUSTOMS_TRACK_COUNTRIES", "US,CN,VN,JP")).split(",") if x.strip()],
                    probe_months=4,
                    history_start=str(env.get("CUSTOMS_HISTORY_START", "1995-01") or "1995-01"),
                    item_country_months=int(env.get("CUSTOMS_ITEM_COUNTRY_MONTHS", "24") or 24),
                ),
                attempts=retry_attempts,
            )
            result["customs"] = f"{update.get('target_month') or '최신월'} 갱신"
        except requests.RequestException as exc:
            error_name = type(exc).__name__
            result["customs"] = f"기존 DB 유지 ({error_name})"
            result["warnings"].append(f"관세청 네트워크 오류: {error_name}")

    refresh_flash_cache(data / "export_flash_cache.csv", verify_ssl=False)
    candidate_mart = data / "investment_mart.candidate.sqlite"
    candidate_share = data / "share_snapshot.candidate.sqlite"
    build = build_analysis_mart(
        raw, candidate_mart,
        data / "motir20_hsk_mti_mapping_2026_full_clean.csv",
        data / "kosis_cycle_cache.csv",
        data / "industry_export_bridge.csv",
    )
    make_share_snapshot(candidate_mart, candidate_share)
    promoted = promote_snapshot(candidate_share, data / "share_snapshot.sqlite")
    os.replace(candidate_mart, data / "investment_mart.sqlite")
    result.update({"ok": True, "build": build, "snapshot": promoted,
                   "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    _write_status(data / "refresh_status.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(run_refresh(Path(__file__).resolve().parent), ensure_ascii=False, indent=2, default=str))
