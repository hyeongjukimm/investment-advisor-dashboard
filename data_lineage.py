from __future__ import annotations


SOURCE_CATALOG = {
    "customs_item": {
        "institution": "관세청",
        "dataset": "관세청_품목별 수출입실적(GW)",
        "operation": "getItemtradeList",
        "field": "expDlr",
        "url": "https://www.data.go.kr/data/15101609/openapi.do",
        "processing": "월·HS10 수출신고 미화금액 → 2026 고정 택소노미 → 선택 분류 합산",
    },
    "customs_country": {
        "institution": "관세청",
        "dataset": "관세청_국가별 수출입실적(GW)",
        "operation": "getNationtradeList",
        "field": "expDlr",
        "url": "https://www.customs.go.kr/kcs/openApi/view.do",
        "processing": "월·국가별 수출신고 미화금액 합산",
    },
    "customs_item_country": {
        "institution": "관세청",
        "dataset": "관세청_품목별 국가별 수출입실적(GW)",
        "operation": "getNitemtradeList",
        "field": "expDlr",
        "url": "https://www.customs.go.kr/kcs/openApi/view.do",
        "processing": "월·국가·HS10 → 대표품목 합산",
    },
    "kosis_cycle": {
        "institution": "국가데이터처",
        "dataset": "KOSIS 광업제조업동향 생산·출하·재고 지수",
        "operation": "statisticsParameterData.do / DT_1F02001",
        "field": "DT",
        "url": "https://kosis.kr/",
        "processing": "산업별 지수 → 12개월 증감률 → 3개월 평균; 재고순환=출하 YoY-재고 YoY",
    },
    "customs_kosis": {
        "institution": "관세청·국가데이터처",
        "dataset": "품목별 수출입실적(GW)·KOSIS 광업제조업동향",
        "operation": "getItemtradeList · DT_1F02001",
        "field": "expDlr · DT",
        "url": "https://kosis.kr/",
        "processing": "Top20 수출과 KSIC 실물지표를 산업 연결표 가중치로 결합",
    },
    "mapping": {
        "institution": "관세청·한국무역협회·산업통상자원부",
        "dataset": "HS10·HSK-MTI 연계·20대 수출품목",
        "operation": "고정 분류표",
        "field": "HSK10 · MTI6 · 20대품목",
        "url": "https://stat.kita.net/",
        "processing": "HS10 → 리서치 중분류 → 대표품목 → 산업부 Top20; 미매핑은 별도 Gap",
    },
    "flash": {
        "institution": "관세청·산업통상자원부",
        "dataset": "월중·월간 수출입 현황",
        "operation": "10일·20일·월말 공표자료",
        "field": "누적 수출·수입 미화금액",
        "url": "https://www.motie.go.kr/kor/article/ATCL3f49a5a8c/list",
        "processing": "동일 체크포인트 기준 전년·전월·5년 평균 비교",
    },
    "internal_exposure": {
        "institution": "내부 리서치",
        "dataset": "company_exposure.csv",
        "operation": "기업 Exposure 매핑",
        "field": "representative_id · product",
        "url": "",
        "processing": "대표품목과 기업 노출 후보 연결; 기업 공시로 별도 검증 필요",
    },
}


def source_caption(key: str) -> str:
    source = SOURCE_CATALOG[key]
    api = f"{source['operation']}, {source['field']}"
    label = f"[{source['dataset']}]({source['url']})" if source["url"] else source["dataset"]
    return f"SOURCE · {label} ({api}) · 가공: {source['processing']}"


def growth_calculation_guide() -> str:
    return """
**원자료와 수출액**  
관세청 `관세청_품목별 수출입실적(GW)`의 월·HS10별 수출신고 미화금액 `expDlr`를 사용합니다. 택소노미와 일치하는 **HS10별 월 수출액의 합**을 대표품목, 리서치 중분류, 산업부 Top20 순서로 합산합니다. `기간수출_억달러 = 선택기간 USD 합계 ÷ 100,000,000`입니다. **미매핑 HS10은 Top20 수출액에서 제외**되고 데이터 점검의 Coverage·Gap에서 따로 확인합니다.

**구간 초→말 3M**  
시작값은 선택 구간의 **첫 3개월 월평균**, 종료값은 **마지막 3개월 월평균**입니다. `성장률=(종료값/시작값-1)×100`, `증가액=종료값-시작값`입니다. 구간이 3개월보다 짧으면 존재하는 월 전체의 평균을 양쪽 비교값으로 사용합니다.

**선택기간 합계 vs 직전 동일기간**  
**현재 선택기간 합계**와 바로 앞의 **직전 동일 길이 기간 합계**를 비교합니다. `성장률=(현재합계/직전합계-1)×100`, `증가액=현재합계-직전합계`입니다.

**기여도와 최소규모**  
`기여도=항목 증가액/전체 항목 증가액 합계×100`입니다. 감소 항목이 섞이면 음수 또는 100% 초과가 가능합니다. 최소 비교규모는 3M 모드에서는 시작 3개월 평균, 동일기간 모드에서는 직전기간 합계에 적용됩니다.
"""


def institution_comparison_guide() -> str:
    return """
| 구분 | 성격 | 이 대시보드와의 관계 |
|---|---|---|
| **산업통상자원부** | 월초 총수출과 주력품목 **잠정** 발표 | 공식 방향 확인용. 정책 품목 범위와 발표 시점이 달라 대시보드 수치와 차이 가능 |
| **관세청** | 수출입 **통관신고** 기반 HS 상세통계 | 대시보드 수출액의 직접 원자료. 정정·취하 반영 시 과거 값도 현행화 |
| **K-stat** | 관세청 무역통계의 HS·MTI **조회·분류** 서비스 | MTI 품목 수치와 매핑을 교차검증하는 참고 기준 |
| **우리 대시보드** | 관세청 HS10을 2026 고정 택소노미로 **재집계** | 동일 분류로 장기 비교하고 Top20→중분류→대표품목 드릴다운 제공 |
| **KOSIS** | 생산·출하·재고 실물지표 | 수출액에 합산하지 않고 산업 연결표를 통해 비교·점수화 |

수치가 다르면 **기준월 → 잠정/확정 → 달러 단위 → HS/MTI 범위 → 미매핑 HS10 → 정정 반영일** 순서로 확인합니다.
"""


_COMMON_EXPORT = "관세청 품목별 수출입실적(GW)의 `expDlr`를 HS10 고정 택소노미로 연결해 합산합니다. 금액은 수출신고 미화금액이며 억달러는 USD÷100,000,000입니다."

PAGE_METHODOLOGY = {
    "종합 현황": f"**사용 데이터** · 관세청 품목별 수출입실적(GW) `getItemtradeList/expDlr`, KOSIS 광업제조업동향 `DT_1F02001/DT`\n\n**산출 방식** · {_COMMON_EXPORT} KOSIS 실물지표는 금액에 합산하지 않고 산업 연결표로 비교합니다.",
    "산업 스크리너": f"**사용 데이터** · 관세청 `getItemtradeList/expDlr`, KOSIS `DT_1F02001/DT`\n\n**산출 방식** · {_COMMON_EXPORT} 펀더멘털 점수는 수출모멘텀 30%, 재고순환 25%, 실물활동 20%, 확산도 15%, 지속성 10%를 가용항목 기준 재가중합니다.",
    "산업 상세": f"**사용 데이터** · 관세청 `getItemtradeList/expDlr`, 연결 KSIC의 KOSIS `DT_1F02001/DT`\n\n**산출 방식** · {_COMMON_EXPORT} YoY는 전년 동월, MoM은 전월과 비교하고 재고순환은 출하 YoY-재고 YoY입니다.",
    "수출 성장": f"**사용 데이터** · 관세청 품목별 수출입실적(GW) `getItemtradeList/expDlr`와 2026 고정 택소노미\n\n**산출 방식** · {_COMMON_EXPORT}\n\n{{growth}}",
    "품목 모니터": f"**사용 데이터** · 관세청 `getItemtradeList/expDlr`, 품목별 국가별 `getNitemtradeList/expDlr·expWgt`\n\n**산출 방식** · {_COMMON_EXPORT} 단가는 수출신고 미화금액÷순중량(USD/kg)입니다.",
    "종목 후보": "**사용 데이터** · 대표품목 택소노미와 내부 company_exposure.csv\n\n**산출 방식** · 대표품목 ID 또는 품목명으로 기업 후보를 연결합니다. 통관액은 기업 매출이 아니므로 공시 검증이 필요합니다.",
    "최근 수출": "**사용 데이터** · 관세청·산업통상자원부 10일·20일·월말 수출입 현황 공표자료\n\n**산출 방식** · 같은 누적 일수끼리 전년·전월·5년 평균과 비교합니다. 월중 수치는 잠정치입니다.",
    "데이터 점검": "**사용 데이터** · 관세청 `getItemtradeList/expDlr` 전체 HS10과 택소노미 매핑 결과\n\n**산출 방식** · Coverage=매핑 HS10 수출액÷전체 HS10 수출액×100, Gap=미매핑 HS10 수출액입니다.",
}


def page_methodology(page: str) -> str:
    text = PAGE_METHODOLOGY[page]
    return text.replace("{growth}", growth_calculation_guide().strip())
