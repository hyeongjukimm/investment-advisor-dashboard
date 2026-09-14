from __future__ import annotations

import re
import pandas as pd

from display_labels import clean_trade_name, shorten_text

_GENERIC_PATTERNS = [
    r"^기타$", r"^부분품$", r"^기타\s*부분품$", r"^기타와\s*그\s*부분품$",
    r"^그\s*밖의\s*것$", r"^그\s*밖의\s*기타$", r"^기타의\s*것$",
]


def _generic(text: str) -> bool:
    t = clean_trade_name(text)
    if not t:
        return True
    return any(re.fullmatch(p, t) for p in _GENERIC_PATTERNS)


def _polish_with_method(official_name, sub_category="", middle_category="", item20="", max_chars: int = 30) -> tuple[str, str]:
    official = clean_trade_name(official_name)
    sub = clean_trade_name(sub_category)
    middle = clean_trade_name(middle_category)
    item = clean_trade_name(item20)
    if official and not _generic(official):
        return shorten_text(official, max_chars), "official"
    for context, method in [(sub, "sub_category"), (middle, "middle_category"), (item, "item20")]:
        if context and not _generic(context):
            return shorten_text(context, max_chars), method
    return shorten_text(official or "기타", max_chars), "fallback"


def polish_hsk_name(official_name, sub_category="", middle_category="", item20="", max_chars: int = 30) -> str:
    return _polish_with_method(official_name, sub_category, middle_category, item20, max_chars)[0]


def build_hsk_label_dictionary(mapping: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "20대품목":"item20", "중분류":"middle_category", "세부분류":"sub_category",
        "MTI6":"mti6", "HSK10":"hsk10", "HS6":"hs6", "HS4":"hs4", "HSK 품목명":"official_name",
    }
    x = mapping.rename(columns={k:v for k,v in rename.items() if k in mapping.columns}).copy()
    for c in ["item20","middle_category","sub_category","mti6","hsk10","hs6","hs4","official_name"]:
        if c not in x.columns:
            x[c] = ""
        x[c] = x[c].fillna("").astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    x["hsk10"] = x["hsk10"].str.zfill(10)
    x = x.drop_duplicates("hsk10").copy()
    polished = x.apply(lambda r: _polish_with_method(r["official_name"], r["sub_category"], r["middle_category"], r["item20"]), axis=1)
    x["display_name"] = polished.map(lambda z: z[0])
    x["label_source"] = polished.map(lambda z: z[1])
    return x[["hsk10","official_name","display_name","label_source","item20","middle_category","sub_category","mti6","hs6","hs4"]].sort_values("hsk10").reset_index(drop=True)
