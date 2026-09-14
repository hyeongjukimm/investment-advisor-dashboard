import pytest

from data_lineage import SOURCE_CATALOG, growth_calculation_guide, institution_comparison_guide, page_methodology, source_caption


def test_source_catalog_identifies_raw_api_field_and_processing():
    item = SOURCE_CATALOG["customs_item"]
    assert item["institution"] == "관세청"
    assert item["dataset"] == "관세청_품목별 수출입실적(GW)"
    assert item["operation"] == "getItemtradeList"
    assert item["field"] == "expDlr"
    assert "HS10" in item["processing"]
    assert "https://www.data.go.kr/data/15101609/openapi.do" == item["url"]


def test_source_caption_is_compact_and_does_not_expose_credentials():
    caption = source_caption("customs_item")
    assert caption.startswith("SOURCE · [관세청_품목별 수출입실적(GW)](")
    assert "https://www.data.go.kr/data/15101609/openapi.do" in caption
    assert "getItemtradeList" in caption
    assert "expDlr" in caption
    assert "apiKey" not in caption
    assert "serviceKey" not in caption


def test_growth_methodology_matches_both_runtime_modes():
    guide = growth_calculation_guide()
    assert "첫 3개월 월평균" in guide
    assert "마지막 3개월 월평균" in guide
    assert "현재 선택기간 합계" in guide
    assert "직전 동일 길이 기간 합계" in guide
    assert "100,000,000" in guide
    assert "미매핑 HS10" in guide


def test_every_page_has_methodology_and_unknown_page_fails():
    pages = ["종합 현황", "산업 스크리너", "산업 상세", "수출 성장", "품목 모니터", "종목 후보", "최근 수출", "데이터 점검"]
    for page in pages:
        assert "**사용 데이터**" in page_methodology(page)
        assert "**산출 방식**" in page_methodology(page)
    with pytest.raises(KeyError):
        page_methodology("없는 화면")

    growth = page_methodology("수출 성장")
    assert "getItemtradeList" in growth
    detail = page_methodology("산업 상세")
    assert "DT_1F02001" in detail


def test_institution_comparison_distinguishes_official_and_dashboard_values():
    guide = institution_comparison_guide()
    assert "산업통상자원부" in guide and "잠정" in guide
    assert "관세청" in guide and "통관신고" in guide
    assert "K-stat" in guide and "조회·분류" in guide
    assert "우리 대시보드" in guide and "재집계" in guide
    assert "KOSIS" in guide and "수출액에 합산하지" in guide
