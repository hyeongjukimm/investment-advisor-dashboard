from __future__ import annotations

import re
from typing import Callable

import requests

KOSIS_BASE_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
KOSIS_CYCLE_TABLE_ID = "DT_1F02001"
KOSIS_SAFE_CHUNK_MONTHS = 12


class KosisApiError(RuntimeError):
    """Raised when KOSIS returns an API/error object instead of observation rows."""

    def __init__(self, message: str, *, err: str | None = None, err_msg: str | None = None):
        super().__init__(message)
        self.err = err
        self.err_msg = err_msg


def build_kosis_url(
    api_key: str,
    months: int | None = 72,
    *,
    start_prd_de: str | None = None,
    end_prd_de: str | None = None,
) -> str:
    """Build the KOSIS request exactly like the known-working legacy app.

    KOSIS multi-select parameters use literal '+' separators, so this function
    intentionally builds the query string instead of passing a params dict.

    For large history requests, pass ``start_prd_de`` and ``end_prd_de``
    (YYYYMM). KOSIS exposes explicit period-range parameters and those are used
    by ``fetch_kosis_history_payload`` to avoid oversized single responses.
    """
    if (start_prd_de is None) != (end_prd_de is None):
        raise ValueError("start_prd_de and end_prd_de must be provided together")

    period_query: str
    if start_prd_de is not None and end_prd_de is not None:
        period_query = f"&startPrdDe={start_prd_de}&endPrdDe={end_prd_de}"
    else:
        if months is None:
            raise ValueError("months is required when an explicit period range is not provided")
        period_query = f"&newEstPrdCnt={int(months)}"

    return (
        f"{KOSIS_BASE_URL}"
        f"?method=getList"
        f"&apiKey={api_key}"
        f"&itmId=T10+T20+T21+T22+"
        f"&objL1=00+"
        f"&objL2=ALL"
        f"&objL3="
        f"&objL4="
        f"&objL5="
        f"&objL6="
        f"&objL7="
        f"&objL8="
        f"&format=json"
        f"&jsonVD=Y"
        f"&prdSe=M"
        f"{period_query}"
        f"&smblChk=N"
        f"&orgId=101"
        f"&tblId={KOSIS_CYCLE_TABLE_ID}"
    )


def redact_api_key(url: str) -> str:
    return re.sub(r"([?&]apiKey=)[^&]*", r"\1***", url)


def _validate_row_payload(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        # KOSIS can return a scalar error/status object for an oversized or
        # otherwise invalid request. Do not pass that to pandas.DataFrame,
        # which produces the cryptic "all scalar values" exception.
        keys = ", ".join(sorted(str(k) for k in payload.keys())[:8]) or "none"
        err = str(payload.get("err", "") or "")
        err_msg = str(payload.get("errMsg", "") or "")
        detail = f" KOSIS 오류 {err}: {err_msg}" if err or err_msg else ""
        raise KosisApiError(
            "KOSIS API returned an object instead of a row list "
            f"(response keys: {keys}).{detail}",
            err=err or None,
            err_msg=err_msg or None,
        )
    raise KosisApiError(
        f"KOSIS API returned {type(payload).__name__} instead of a row list"
    )


def fetch_kosis_payload(
    api_key: str,
    months: int = 72,
    verify_ssl: bool = False,
    get: Callable = requests.get,
):
    url = build_kosis_url(api_key, months)
    response = get(url, timeout=30, verify=verify_ssl)
    response.raise_for_status()
    payload = _validate_row_payload(response.json())
    return payload, url


def fetch_kosis_range_payload(
    api_key: str,
    start_prd_de: str,
    end_prd_de: str,
    verify_ssl: bool = False,
    get: Callable = requests.get,
):
    url = build_kosis_url(
        api_key,
        months=None,
        start_prd_de=start_prd_de,
        end_prd_de=end_prd_de,
    )
    response = get(url, timeout=30, verify=verify_ssl)
    response.raise_for_status()
    payload = _validate_row_payload(response.json())
    return payload, url


def _ym_to_index(ym: str) -> int:
    if not re.fullmatch(r"\d{6}", str(ym)):
        raise ValueError(f"Expected YYYYMM period, got {ym!r}")
    year = int(str(ym)[:4])
    month = int(str(ym)[4:6])
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid month in period {ym!r}")
    return year * 12 + (month - 1)


def _index_to_ym(index: int) -> str:
    year, month0 = divmod(index, 12)
    return f"{year:04d}{month0 + 1:02d}"


def fetch_kosis_history_payload(
    api_key: str,
    months: int = 720,
    *,
    chunk_months: int = 120,
    verify_ssl: bool = False,
    get: Callable = requests.get,
):
    """Fetch a long KOSIS monthly history in bounded period chunks.

    A single long request for DT_1F02001 can exceed KOSIS's response-cell
    limit. This function caps each explicit range at 60 months, first discovers
    the latest available period with a
    one-period call, then requests non-overlapping explicit date ranges and
    combines the returned observation rows.
    """
    months = int(months)
    chunk_months = min(int(chunk_months), KOSIS_SAFE_CHUNK_MONTHS)
    if months <= 0:
        return [], []
    if chunk_months <= 0:
        raise ValueError("chunk_months must be positive")

    latest_payload, latest_url = fetch_kosis_payload(
        api_key=api_key,
        months=1,
        verify_ssl=verify_ssl,
        get=get,
    )
    periods = [
        str(row.get("PRD_DE", ""))
        for row in latest_payload
        if isinstance(row, dict) and re.fullmatch(r"\d{6}", str(row.get("PRD_DE", "")))
    ]
    if not periods:
        return latest_payload, [latest_url]

    latest_idx = max(_ym_to_index(ym) for ym in periods)
    first_idx = latest_idx - (months - 1)

    rows = []
    urls = [latest_url]
    cursor = first_idx
    while cursor <= latest_idx:
        end_idx = min(cursor + chunk_months - 1, latest_idx)
        start_ym = _index_to_ym(cursor)
        end_ym = _index_to_ym(end_idx)
        try:
            payload, url = fetch_kosis_range_payload(
                api_key=api_key,
                start_prd_de=start_ym,
                end_prd_de=end_ym,
                verify_ssl=verify_ssl,
                get=get,
            )
        except KosisApiError as exc:
            if exc.err == "30" or "데이터가 존재하지 않습니다" in str(exc.err_msg or ""):
                cursor = end_idx + 1
                continue
            raise
        rows.extend(payload)
        urls.append(url)
        cursor = end_idx + 1

    return rows, urls
