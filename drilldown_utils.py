from __future__ import annotations

import pandas as pd

ALL_OPTION = "전체"


def _unique_strings(series: pd.Series) -> list[str]:
    return series.dropna().astype(str).drop_duplicates().tolist()


def drilldown_options(dims: pd.DataFrame, item20: str, middle_category: str = ALL_OPTION) -> tuple[list[str], list[str]]:
    item_rows = dims[dims["item20"].astype(str) == str(item20)]
    middle_options = [ALL_OPTION] + _unique_strings(item_rows["middle_category"])
    if middle_category == ALL_OPTION:
        return middle_options, [ALL_OPTION]
    middle_rows = item_rows[item_rows["middle_category"].astype(str) == str(middle_category)]
    product_options = [ALL_OPTION] + _unique_strings(middle_rows["product"])
    return middle_options, product_options


def product_monitor_selection(item20: str, middle_category: str, product: str) -> tuple[str, str, tuple[str, ...], str]:
    if middle_category == ALL_OPTION:
        return "mart_export_top20_monthly", "AND item20=?", (item20,), item20
    if product == ALL_OPTION:
        return (
            "mart_export_middle_monthly",
            "AND item20=? AND middle_category=?",
            (item20, middle_category),
            middle_category,
        )
    return (
        "mart_export_product_monthly",
        "AND item20=? AND middle_category=? AND product=?",
        (item20, middle_category, product),
        product,
    )
