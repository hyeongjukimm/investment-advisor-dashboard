# Dashboard Data Lineage Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모든 차트에 정확한 소형 출처 캡션을 표시하고, 페이지별 토글과 가이드북에서 원자료·API·산식을 설명한다.

**Architecture:** `data_lineage.py`가 출처와 산출 기준의 단일 원천이 된다. `app.py`의 공통 차트 렌더러와 페이지 렌더러가 이를 사용하고, 가이드북도 같은 설명을 재사용한다.

**Tech Stack:** Python 3.12, Streamlit, pandas, Plotly, pytest

**Spec:** `docs/superpowers/specs/2026-09-14-data-lineage-guide-design.md`

## Global Constraints

- 차트 출처는 작은 회색 캡션으로 항상 표시한다.
- 페이지 산출 기준은 기본 접힘 토글이다.
- 공식 기관명, 데이터셋명, API 작업명, 원필드, 단위와 가공 방식을 구분한다.
- API 키와 실제 요청 URL은 표시하지 않는다.

---

### Task 1: 중앙 데이터 계보 목록

**Files:**
- Create: `data_lineage.py`
- Create: `tests/test_data_lineage.py`

**Interfaces:**
- Produces: `source_caption(key: str) -> str`, `page_methodology(page: str) -> str`, `growth_calculation_guide() -> str`

- [ ] 출처 키별 기관·데이터셋·API·원필드·가공 방식과 페이지별 산식을 검증하는 실패 테스트를 작성한다.
- [ ] `python -m pytest tests/test_data_lineage.py -q`로 누락 함수 실패를 확인한다.
- [ ] 관세청 품목·국가·품목국가 API, KOSIS `DT_1F02001`, 산업부·KITA, 내부 매핑 메타데이터를 구현한다.
- [ ] 단위, 두 성장 모드, 기여도, 미매핑 제외 설명을 구현한다.
- [ ] 집중 테스트를 통과시킨다.

### Task 2: 차트별 소형 출처 캡션

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app_presentation.py`

**Interfaces:**
- Consumes: `source_caption(key)`
- Produces: `render_chart(..., source_key: str)`

- [ ] 모든 차트 호출이 `source_key`를 제공한다는 실패 테스트를 작성한다.
- [ ] `render_chart`가 차트와 CSV 버튼 아래에 `.source-note` 캡션을 출력하도록 구현한다.
- [ ] 수출·KOSIS·혼합·최근수출·내부매핑 차트에 맞는 출처 키를 연결한다.
- [ ] 집중 테스트를 통과시킨다.

### Task 3: 페이지별 산출 기준 토글과 가이드북

**Files:**
- Modify: `app.py`
- Modify: `dashboard_utils.py`
- Modify: `tests/test_dashboard_utils.py`

**Interfaces:**
- Consumes: `page_methodology(page)`, `growth_calculation_guide()`
- Produces: 각 페이지의 `데이터·산출 기준` 토글과 기능별 가이드북

- [ ] 가이드북의 페이지 항목과 성장 산식 설명에 대한 실패 테스트를 완성한다.
- [ ] 각 페이지 첫 부분에 기본 접힘 토글을 추가한다.
- [ ] 기관 발표치 차이와 `HS10 → 중분류 → 대표품목 → Top20` 계보를 가이드북에 추가한다.
- [ ] 집중 테스트를 통과시킨다.

### Task 4: 통합 검증과 배포

**Files:**
- Modify: 위 구현 파일

- [ ] `python -m pytest -q`를 실행해 전체 테스트를 통과시킨다.
- [ ] `python -m py_compile app.py dashboard_utils.py data_lineage.py`를 실행한다.
- [ ] Streamlit을 headless 모드로 기동해 서버 시작을 확인한다.
- [ ] 변경을 커밋하고 GitHub `main`에 반영한다.
- [ ] GitHub의 파일 blob SHA가 로컬 결과와 일치하는지 확인한다.
