from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pandas as pd
import urllib3

from customs_pipeline import CustomsClient, probe_latest_item_data, standardize_mapping
from kosis_client import fetch_kosis_payload

BASE_DIR = Path(__file__).resolve().parent
MAPPING_PATH = BASE_DIR / "data" / "motir20_hsk_mti_mapping_2026.csv"


def load_project_secrets(base_dir: str | Path = BASE_DIR) -> dict:
    path = Path(base_dir) / ".streamlit" / "secrets.toml"
    if not path.exists():
        raise FileNotFoundError(f"secrets.toml not found: {path}")
    with path.open("rb") as f:
        return tomllib.load(f)


def _ok(msg: str) -> None:
    print(f"[PASS] {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def run_diagnostics(base_dir: str | Path = BASE_DIR) -> int:
    base_dir = Path(base_dir)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print("=" * 72)
    print("Investment Advisor · connection diagnostics")
    print("Keys are never printed.")
    print("=" * 72)

    try:
        cfg = load_project_secrets(base_dir)
    except Exception as exc:
        _fail(str(exc))
        return 2

    kosis_key = str(cfg.get("KOSIS_API_KEY", "")).strip()
    customs_key = str(cfg.get("CUSTOMS_SERVICE_KEY", "")).strip()
    if not kosis_key:
        _fail("KOSIS_API_KEY is missing")
    else:
        _ok("KOSIS_API_KEY loaded from project secrets")
    if not customs_key:
        _fail("CUSTOMS_SERVICE_KEY is missing")
    else:
        _ok("CUSTOMS_SERVICE_KEY loaded from project secrets")
    if not kosis_key or not customs_key:
        return 2

    if not MAPPING_PATH.exists():
        _fail(f"Mapping file missing: {MAPPING_PATH}")
        return 2

    try:
        raw_map = pd.read_csv(MAPPING_PATH, dtype=str)
        mapping = standardize_mapping(raw_map)
        n20 = int(mapping["item20"].nunique())
        unique_hsk = bool(mapping["hsk10"].is_unique)
        if n20 == 20 and unique_hsk:
            _ok(f"Mapping QC: {len(mapping):,} unique HSK10 / 20 categories")
        else:
            _fail(f"Mapping QC failed: {len(mapping):,} rows / {n20} categories / unique={unique_hsk}")
            return 3
    except Exception as exc:
        _fail(f"Mapping load failed: {type(exc).__name__}: {exc}")
        return 3

    # KOSIS connectivity
    try:
        payload, _ = fetch_kosis_payload(kosis_key, months=12, verify_ssl=False)
        if isinstance(payload, list) and len(payload) > 0:
            _ok(f"KOSIS live response: {len(payload):,} rows")
        else:
            _warn("KOSIS responded but returned no rows")
    except Exception as exc:
        _warn(f"KOSIS live check failed: {type(exc).__name__}: {exc}")

    # Customs: use the same broad HSK probe that the app depends on.
    try:
        client = CustomsClient(customs_key, verify_ssl=False, timeout=90)
        probe = probe_latest_item_data(client, lookback_months=4)
        item_df = probe["data"]
        latest = probe["latest_month"]
        if latest is None or item_df.empty:
            _fail(
                "Customs item API authenticated but no HSK rows were returned in the recent 4-month probe"
            )
            return 4

        latest_rows = item_df[item_df["date"] == latest].copy()
        latest_rows["hsk10"] = latest_rows["hsk10"].astype(str).str.zfill(10)
        joined = latest_rows.merge(mapping[["hsk10", "item20"]], on="hsk10", how="inner")
        observed = sorted(joined["item20"].dropna().astype(str).unique().tolist())
        expected = sorted(mapping["item20"].dropna().astype(str).unique().tolist())
        missing = sorted(set(expected) - set(observed))

        _ok(
            f"Customs item API live: latest={latest:%Y-%m}, raw HSK rows={len(latest_rows):,}, mapped rows={len(joined):,}"
        )
        if len(observed) == 20:
            _ok("20/20 export-category coverage on latest detected month")
        else:
            _fail(f"20대 coverage {len(observed)}/20; missing: {', '.join(missing) if missing else '-'}")
            print("This means the API response itself is incomplete for the app's HSK10 aggregation path.")
            return 5
    except Exception as exc:
        _fail(f"Customs live check failed: {type(exc).__name__}: {exc}")
        return 4

    print("=" * 72)
    print("READY: API credentials, mapping, and Customs HSK 20/20 path are usable.")
    print("Next: python -m streamlit run app.py")
    return 0


def main() -> None:
    raise SystemExit(run_diagnostics())


if __name__ == "__main__":
    main()
