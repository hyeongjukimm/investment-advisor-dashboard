import pandas as pd

from display_labels import (
    clean_trade_name,
    shorten_text,
    build_level_label_map,
    format_code_label,
)


def test_clean_trade_name_removes_parenthetical_and_external_count():
    raw = '롤 라미네이터(인쇄회로기판이나 인쇄회로 제조에 전용 또는 주로 사용되는 종류의 것으로 한정한다) / 고무 공업용 / 플라스틱 공업용 외 5개'
    cleaned = clean_trade_name(raw)
    assert '한정한다' not in cleaned
    assert '외 5개' not in cleaned
    assert cleaned.startswith('롤 라미네이터')


def test_shorten_text_caps_long_names_without_cutting_into_noise():
    raw = '마이크로프로세서, 전기통신용 기기, 자동자료처리기계 또는 자동자료처리기계의 단위기기 냉각을 위해 전용 또는 주로 사용되는 것'
    short = shorten_text(raw, max_chars=22)
    assert len(short) <= 23
    assert short.endswith('…')


def test_middle_level_uses_curated_override_for_known_mti4():
    df = pd.DataFrame(
        {
            'item20': ['컴퓨터', '컴퓨터'],
            'middle_category': ['MTI4 8138', 'MTI4 8138'],
            'mti6': ['813800', '813800'],
            'hs6': ['852329', '852351'],
            'mapping_name': ['기록이 안 된 매체', '마그네틱 스트라이프를 갖춘 카드'],
        }
    )
    labels = build_level_label_map(df, 'middle_category')
    assert labels['MTI4 8138'] == '기록매체 (8138)'


def test_middle_level_auto_generates_short_representative_label():
    df = pd.DataFrame(
        {
            'item20': ['석유화학'] * 3,
            'middle_category': ['MTI4 2120'] * 3,
            'mti6': ['211010', '211020', '211030'],
            'hs6': ['290121', '290122', '290124'],
            'mapping_name': ['에틸렌', '프로펜(프로필렌)', '1,3-부타디엔'],
        }
    )
    labels = build_level_label_map(df, 'middle_category')
    assert labels['MTI4 2120'].startswith('에틸렌·프로펜')
    assert labels['MTI4 2120'].endswith('(2120)')


def test_subcategory_long_label_is_shortened_and_code_can_be_appended():
    label = format_code_label(
        '방직기계용 보빈(bobbin) / 직물용 / 방사(紡絲)기 외 46개',
        '713100',
        max_chars=24,
    )
    assert len(label) < 40
    assert '외 46개' not in label
    assert '(713100)' in label


def test_external_override_file_can_replace_default(tmp_path):
    from display_labels import load_label_overrides

    p = tmp_path / 'labels.csv'
    p.write_text('level,code,short_name\nMTI4,8138,저장·기록매체\n', encoding='utf-8')
    ov = load_label_overrides(p)
    assert ov['MTI4']['8138'] == '저장·기록매체'


def test_generated_middle_label_is_compact_and_html_clean():
    df = pd.DataFrame({
        'item20': ['석유화학', '석유화학'],
        'middle_category': ['MTI4 2130', 'MTI4 2130'],
        'mti6': ['213010', '213020'],
        'hs6': ['290531', '290941'],
        'mapping_name': ['에틸렌글리콜', '2,2&acute;-옥시디에탄올과 디에틸렌글리콜'],
    })
    label = build_level_label_map(df, 'middle_category')['MTI4 2130']
    assert '&' not in label
    assert len(label) <= 34
