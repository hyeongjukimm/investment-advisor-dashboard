from __future__ import annotations

import math
from typing import Any

import pandas as pd

USD_PER_100M = 100_000_000.0


def sidebar_guide_sections() -> dict[str, str]:
    """Return the feature-level Korean guide rendered in the guidebook dialog."""
    return {
        "처음 보는 분을 위한 빠른 시작": """
1. **종합 현황**에서 실물경기와 수출의 큰 방향을 확인합니다.
2. **산업 스크리너**에서 개선 산업을 고릅니다.
3. **산업 상세 → 품목 모니터 → 종목 후보** 순서로 내려갑니다.
4. 상단의 빠른 기간 또는 시작·종료일을 바꾸면 선택 기간 기준으로 다시 계산됩니다.
5. 각 차트 아래 **CSV** 버튼으로 현재 표시 데이터를 받을 수 있습니다.
""",
        "종합 현황": """
한국 총수출과 Top20 합계, 수출 모멘텀, 산업별 실물경기를 한 화면에서 비교합니다. 먼저 방향을 확인한 뒤 세부 화면으로 이동하는 출발점입니다.

**데이터 출처** · [KOSIS 국가통계포털](https://kosis.kr/) · [관세청 OpenAPI](https://www.customs.go.kr/kcs/openApi/view.do) · [산업통상자원부](https://www.motie.go.kr/)
""",
        "산업 스크리너": """
선택 기간의 산업별 펀더멘털 점수, 수출 YoY, 재고순환, 실물·수출 동반개선을 비교합니다. 순위는 주가 전망이 아니라 **실물·수출 선별 신호**입니다.

**데이터 출처** · [KOSIS 국가통계포털](https://kosis.kr/) · [관세청 OpenAPI](https://www.customs.go.kr/kcs/openApi/view.do)
""",
        "산업 상세": """
선택 산업의 생산·출하·재고와 수출 흐름을 같은 기간으로 맞춰 봅니다. 수출 증가가 실제 생산·출하 개선으로 이어지는지 확인할 때 사용합니다.

**데이터 출처** · [KOSIS 국가통계포털](https://kosis.kr/) · [관세청 OpenAPI](https://www.customs.go.kr/kcs/openApi/view.do)
""",
        "수출 성장": """
선택 기간의 산업별 수출 성장률을 비교합니다. 짧은 구간의 기저효과가 클 수 있으므로 수출액 규모와 지속성을 함께 확인해야 합니다.

**데이터 출처** · [관세청 OpenAPI](https://www.customs.go.kr/kcs/openApi/view.do) · [산업통상자원부 수출입 동향](https://www.motie.go.kr/kor/article/ATCL3f49a5a8c/list)
""",
        "품목 모니터": """
산업부 Top20에서 리서치 중분류와 대표품목까지 내려가 수출액·증가율을 확인합니다. HS10 여러 개를 업계에서 읽기 쉬운 대표품목으로 묶은 결과입니다.

**데이터 출처** · [관세청 OpenAPI](https://www.customs.go.kr/kcs/openApi/view.do) · [K-stat 무역통계](https://stat.kita.net/) · [산업통상자원부](https://www.motie.go.kr/)
""",
        "종목 후보": """
대표품목과 관련 기업의 매출 노출 가능성을 연결해 조사 후보를 만듭니다. 자동 매수 신호가 아니며 기업 공시·사업보고서로 실제 노출을 재검증해야 합니다.

**데이터 출처** · 관세청 품목 수출통계 · 내부 `company_exposure.csv` 매핑
""",
        "최근 수출": """
당월 10일·20일·월말 누적 수출을 전년·전월·5년 평균과 비교합니다. 월중 값은 잠정치이며 조업일수 차이를 함께 봐야 합니다.

**데이터 출처** · [산업통상자원부 수출입 동향](https://www.motie.go.kr/kor/article/ATCL3f49a5a8c/list) · [관세청](https://www.customs.go.kr/)
""",
        "지표·점수 해석": """
- **YoY**: 전년 같은 달 대비 증감률
- **MoM**: 직전 달 대비 증감률
- **재고순환**: 출하 YoY − 재고 YoY. 높아질수록 수요·재고 여건 개선 신호
- **동반개선**: 실물지표와 수출지표가 함께 개선된 산업
- **펀더멘털 점수**: 수출 성장·확산도·지속성·재고순환을 합산한 선별 점수. 주가·EPS·수급은 포함하지 않음
""",
        "분류·매핑 확인": """
기본 연결은 **HS10 → 리서치 중분류 → 대표품목 → 산업부 Top20** 순서입니다. 관세청 HS10 원자료를 업계에서 읽기 쉬운 품목명으로 묶고, 산업부 20대 수출품목에 연결한 **2026 고정 택소노미**를 사용합니다.

- 앱 확인: **데이터 점검 → Taxonomy 샘플**
- 전체 매핑: `data/motir20_hsk_mti_mapping_2026_full_clean.csv`
- 표시명·업계분류: `data/hsk10_display_labels_2026.csv`
- KOSIS-수출 산업 연결: `data/industry_export_bridge.csv`

HS 분류는 통관 품목 기준이므로 기업 매출·주가 노출과 완전히 같지 않습니다. 기업 연결은 별도 Exposure 자료와 함께 검증해야 합니다.
""",
        "데이터 갱신·웹 반영": """
GitHub Actions가 매일 **한국시간 오전 8시 30분** 최신 데이터를 확인합니다. 화면 왼쪽의 수출·KOSIS 기준월과 Mart 생성시각으로 반영 여부를 확인하세요.

화면 수정은 로컬 코드 변경 후 GitHub Desktop에서 **Commit to main → Push origin** 순서로 올리면 같은 Streamlit 주소에 자동 반영됩니다. 수정 전에는 **Fetch origin → Pull origin**으로 최신 상태를 먼저 받으세요.
""",
        "데이터 한계와 주의사항": """
- 최신 수출월과 KOSIS 공표월은 발표 시차 때문에 다를 수 있습니다.
- HS10은 통관 분류이며 기업의 제품·매출 분류와 일치하지 않을 수 있습니다.
- YoY 급등은 낮은 전년 기저에서 발생할 수 있으므로 수출액과 장기 추세를 함께 확인합니다.
- 펀더멘털 점수는 아이디어 선별용이며 주가·밸류에이션·실적 전망을 대신하지 않습니다.
""",
    }


def _month_start(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        raise ValueError("date cannot be NaT")
    return ts.to_period("M").to_timestamp()


def normalize_month_range(start: Any, end: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Normalize two date-like values to ordered month-start timestamps."""
    s = _month_start(start)
    e = _month_start(end)
    return (s, e) if s <= e else (e, s)


def quick_month_range(latest: Any, preset: str, available_start: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return an inclusive monthly range ending at ``latest`` for common presets."""
    end = _month_start(latest)
    floor = _month_start(available_start)
    if preset == "전체":
        return min(floor, end), end
    months_by_preset = {"1Y": 12, "3Y": 36, "5Y": 60, "10Y": 120}
    if preset not in months_by_preset:
        raise ValueError(f"unsupported preset: {preset}")
    months = months_by_preset[preset]
    start = end - pd.DateOffset(months=months - 1)
    return max(start, floor), end


def filter_month_range(df: pd.DataFrame, start: Any, end: Any, date_col: str = "date") -> pd.DataFrame:
    """Filter a frame to an inclusive month range without mutating the source."""
    if df.empty or date_col not in df.columns:
        return df.copy()
    s, e = normalize_month_range(start, end)
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    return out[(out[date_col] >= s) & (out[date_col] <= e)].copy()


def industry_period_summary(signal: pd.DataFrame) -> pd.DataFrame:
    """Attach selected-period average and change to each industry's latest row."""
    if signal.empty:
        return signal.copy()
    work = signal.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work["fundamental_score"] = pd.to_numeric(work["fundamental_score"], errors="coerce")
    work = work.dropna(subset=["date", "item20"]).sort_values(["item20", "date"])
    latest = work.groupby("item20", as_index=False).tail(1).copy()
    stats = work.groupby("item20", as_index=False).agg(
        period_avg_score=("fundamental_score", "mean"),
        period_first_score=("fundamental_score", "first"),
    )
    out = latest.merge(stats, on="item20", how="left")
    out["period_change_score"] = out["fundamental_score"] - out["period_first_score"]
    return out


def usd_to_100m(value: Any):
    """Convert raw USD to 100-million-USD units (억달러)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return float(value) / USD_PER_100M


def format_100m_usd(value: Any, decimals: int = 1) -> str:
    converted = usd_to_100m(value)
    if converted is None or not math.isfinite(converted):
        return "-"
    return f"{converted:,.{int(decimals)}f}억달러"
