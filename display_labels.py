from __future__ import annotations

import html
import re
from collections import Counter
from pathlib import Path
from typing import Dict

import pandas as pd


# High-value / frequently viewed groups. These are display labels only; codes stay authoritative.
MTI4_OVERRIDES: Dict[str, str] = {
    # Semiconductors
    "8311": "메모리반도체",
    "8312": "시스템반도체",
    "8313": "개별소자반도체",
    "8314": "실리콘웨이퍼",
    # Computers
    "8131": "컴퓨터",
    "8132": "저장장치",
    "8133": "프린터",
    "8134": "모니터",
    "8135": "입출력장치",
    "8136": "컴퓨터부품",
    "8137": "기록매체·SW",
    "8138": "기록매체",
    # Petroleum / petrochemical representative groups
    "1331": "휘발유",
    "1332": "등유",
    "1333": "경유",
    "1334": "중유",
    "1335": "나프타",
    "2110": "기초유분",
    # Auto parts
    "7420": "자동차부품",
    "7421": "자동차부품",
}

_GENERIC = {
    "기타",
    "부분품",
    "자동차용",
    "제87류의 차량용",
    "제87류 차량용",
    "신품",
    "중고품",
}


def load_label_overrides(path) -> Dict[str, Dict[str, str]]:
    path = Path(path)
    result: Dict[str, Dict[str, str]] = {}
    if not path.exists():
        return result
    df = pd.read_csv(path, dtype=str).fillna("")
    required = {"level", "code", "short_name"}
    if not required.issubset(df.columns):
        return result
    for _, row in df.iterrows():
        level = str(row["level"]).strip().upper()
        code = str(row["code"]).strip()
        name = str(row["short_name"]).strip()
        if level and code and name:
            result.setdefault(level, {})[code] = name
    return result


_DEFAULT_OVERRIDE_PATH = Path(__file__).resolve().parent / "data" / "display_label_overrides.csv"
EXTERNAL_OVERRIDES = load_label_overrides(_DEFAULT_OVERRIDE_PATH)


def _strip_parenthetical(text: str) -> str:
    # Repeatedly remove short explanatory parentheses. This is for display only.
    prev = None
    out = text
    while prev != out:
        prev = out
        out = re.sub(r"\([^()]{0,120}\)", "", out)
        out = re.sub(r"\[[^\[\]]{0,120}\]", "", out)
    return out


def clean_trade_name(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = html.unescape(str(value).strip())
    text = text.replace("ㆍ", "·")
    text = _strip_parenthetical(text)
    text = re.sub(r"\s*외\s*\d+개\s*$", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*/\s*", " / ", text)
    return text.strip(" /·,")


def shorten_text(value, max_chars: int = 24) -> str:
    text = clean_trade_name(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _candidate_terms(series: pd.Series, max_terms: int = 2) -> list[str]:
    candidates: list[str] = []
    seen = set()
    for raw in series.dropna().astype(str):
        cleaned = clean_trade_name(raw)
        for part in [p.strip() for p in cleaned.split("/") if p.strip()]:
            part = shorten_text(part, 15)
            if not part or part in _GENERIC or len(part) <= 1:
                continue
            if part not in seen:
                seen.add(part)
                candidates.append(part)
            if len(candidates) >= max_terms:
                return candidates
    return candidates


def format_code_label(name, code: str | None = None, max_chars: int = 24) -> str:
    short = shorten_text(name, max_chars=max_chars)
    code = "" if code is None else str(code).strip()
    return f"{short} ({code})" if code else short


def build_level_label_map(detail: pd.DataFrame, level_col: str) -> Dict[str, str]:
    if detail.empty or level_col not in detail.columns:
        return {}

    result: Dict[str, str] = {}
    keys = detail[level_col].fillna("").astype(str).str.strip()

    for key in keys[keys != ""].drop_duplicates().tolist():
        group = detail[keys == key]

        if level_col == "middle_category":
            m = re.fullmatch(r"MTI4\s+(\d{4})", key)
            if m:
                code = m.group(1)
                external = EXTERNAL_OVERRIDES.get("MTI4", {}).get(code)
                if external:
                    result[key] = f"{external} ({code})"
                    continue
                if code in MTI4_OVERRIDES:
                    result[key] = f"{MTI4_OVERRIDES[code]} ({code})"
                    continue
                terms = _candidate_terms(group.get("mapping_name", pd.Series(dtype=str)), 2)
                if terms:
                    combined = shorten_text("·".join(terms), 22)
                    result[key] = f"{combined} ({code})"
                else:
                    item20 = str(group.get("item20", pd.Series(["세부품목"])).iloc[0] or "세부품목")
                    result[key] = f"{shorten_text(item20, 14)} 세부 ({code})"
            else:
                result[key] = shorten_text(key, 20)
            continue

        if level_col == "sub_category":
            # For generated long subcategories, keep at most two representative terms.
            terms = [p.strip() for p in clean_trade_name(key).split("/") if p.strip()]
            terms = [shorten_text(p, 15) for p in terms if p not in _GENERIC]
            if terms:
                result[key] = "·".join(terms[:2])
            else:
                result[key] = shorten_text(key, 24)
            continue

        if level_col == "mti6":
            names = _candidate_terms(group.get("sub_category", pd.Series(dtype=str)), 1)
            if not names:
                names = _candidate_terms(group.get("mapping_name", pd.Series(dtype=str)), 1)
            result[key] = f"{names[0]} ({key})" if names else key
            continue

        if level_col == "hs6":
            names = _candidate_terms(group.get("mapping_name", pd.Series(dtype=str)), 1)
            result[key] = f"{names[0]} ({key})" if names else key
            continue

        result[key] = shorten_text(key, 24)

    return result
