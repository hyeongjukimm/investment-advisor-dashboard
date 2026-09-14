import pandas as pd

from hsk_labels import polish_hsk_name, build_hsk_label_dictionary


def test_generic_hsk_name_uses_subcategory_context():
    label = polish_hsk_name("기타", "기타 메모리반도체", "메모리반도체", "반도체")
    assert label == "기타 메모리반도체"


def test_informative_hsk_name_is_preserved_compactly():
    label = polish_hsk_name("플래시 메모리", "낸드/플래시 메모리", "메모리반도체", "반도체")
    assert label == "플래시 메모리"


def test_dictionary_preserves_official_and_generates_unique_hsk_rows():
    mapping = pd.DataFrame([
        {"HSK10":"1", "20대품목":"반도체", "중분류":"메모리반도체", "세부분류":"기타 메모리반도체", "MTI6":"831190", "HS6":"854232", "HS4":"8542", "HSK 품목명":"기타"},
        {"HSK10":"2", "20대품목":"반도체", "중분류":"메모리반도체", "세부분류":"낸드/플래시 메모리", "MTI6":"831120", "HS6":"854232", "HS4":"8542", "HSK 품목명":"플래시 메모리"},
    ])
    out = build_hsk_label_dictionary(mapping)
    assert out["hsk10"].tolist() == ["0000000001", "0000000002"]
    assert out.loc[0, "official_name"] == "기타"
    assert out.loc[0, "display_name"] == "기타 메모리반도체"

def test_generated_full_dictionary_covers_mapping_universe():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    labels = pd.read_csv(root / "data" / "hsk10_display_labels_2026.csv", dtype=str)
    mapping = pd.read_csv(root / "data" / "motir20_hsk_mti_mapping_2026.csv", dtype=str)
    assert len(labels) == mapping["HSK10"].nunique() == 8178
    assert labels["hsk10"].is_unique
    assert labels["display_name"].fillna("").str.strip().ne("").all()
