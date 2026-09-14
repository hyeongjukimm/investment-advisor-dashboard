# Investment Advisor Web Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 링크 접속만으로 최신 검증 데이터를 조회하는 읽기 전용 Streamlit 배포본과 반복 가능한 갱신 절차를 만든다.

**Architecture:** 웹 앱은 `data/share_snapshot.sqlite`만 읽고 API 키·원본 DB·갱신 버튼을 노출하지 않는다. 사용자 PC 또는 예약 실행 환경이 원본 DB를 갱신한 뒤 임시 공유 Mart를 만들고 검증을 통과한 경우에만 배포 파일을 원자적으로 교체한다.

**Tech Stack:** Python 3.11+, Streamlit, SQLite, pandas, pytest, GitHub Actions, Streamlit Community Cloud

**Spec:** `/workspace/scratch/8365ae848aea/investment_advisor_web_deployment_design.md`

## Global Constraints

- 실제 API 키와 `.streamlit/secrets.toml`은 저장소와 ZIP에 포함하지 않는다.
- `data/investment_advisor.sqlite`와 임시 DB는 저장소에서 제외한다.
- 공개 앱은 공유 Mart에 대한 읽기만 수행한다.
- 데이터 갱신 실패 시 마지막 정상 공유 Mart를 유지한다.
- 모든 사용자 노출 상태·오류 문구는 한글로 표시한다.

---

### Task 1: 배포 모드 경계

**Files:**
- Create: `deployment_mode.py`
- Modify: `app.py`
- Test: `tests/test_deployment_mode.py`

**Interfaces:**
- Consumes: `SHARED_MODE` 환경변수 또는 Streamlit secret
- Produces: `is_shared_mode(value) -> bool`, `allow_admin_controls(shared, raw_exists) -> bool`

- [ ] 환경값 `true/1/yes/on`만 공유 모드로 해석하고 공유 모드에서 관리자 버튼을 차단하는 실패 테스트를 작성한다.
- [ ] `python -m pytest tests/test_deployment_mode.py -q`로 실패를 확인한다.
- [ ] 두 순수 함수를 구현하고 `app.py`의 사이드바 관리자 제어에 적용한다.
- [ ] 같은 테스트를 실행해 통과를 확인한다.
- [ ] `git add deployment_mode.py app.py tests/test_deployment_mode.py && git commit -m "feat: isolate shared deployment mode"`로 커밋한다.

### Task 2: 공유 Mart 검증과 원자적 교체

**Files:**
- Create: `validate_snapshot.py`
- Modify: `make_portable.py`
- Test: `tests/test_validate_snapshot.py`

**Interfaces:**
- Consumes: SQLite 파일 경로
- Produces: `validate_snapshot(path) -> dict`, `promote_snapshot(candidate, target) -> dict`

- [ ] 필수 테이블 누락·빈 Top20·정상 DB·실패 시 기존 파일 보존을 재현하는 테스트를 작성한다.
- [ ] `python -m pytest tests/test_validate_snapshot.py -q`로 실패를 확인한다.
- [ ] `PRAGMA quick_check`, 필수 테이블, 행 수, 최신월을 검사하고 `os.replace`로 정상 후보만 교체한다.
- [ ] `make_portable.py`가 검증된 snapshot만 ZIP에 넣도록 연결한다.
- [ ] 테스트 통과 후 `git add validate_snapshot.py make_portable.py tests/test_validate_snapshot.py && git commit -m "feat: validate and promote share snapshots"`로 커밋한다.

### Task 3: 자동 갱신 실행기

**Files:**
- Create: `scheduled_refresh.py`
- Test: `tests/test_scheduled_refresh.py`

**Interfaces:**
- Consumes: `KOSIS_API_KEY`, `CUSTOMS_SERVICE_KEY`, 기존 원본 DB와 캐시
- Produces: `run_refresh(base_dir) -> dict`, 종료코드 0/1

- [ ] API 키가 없는 경우 기존 DB로 Mart만 생성하고, 갱신 실패 시 공유본을 교체하지 않는 테스트를 작성한다.
- [ ] `python -m pytest tests/test_scheduled_refresh.py -q`로 실패를 확인한다.
- [ ] 기존 클라이언트와 Mart builder를 호출해 후보 snapshot 생성·검증·교체·JSON 상태 저장을 구현한다.
- [ ] 키·URL을 로그에서 마스킹하고 실제 KOSIS `err/errMsg`만 남긴다.
- [ ] 테스트 통과 후 `git add scheduled_refresh.py tests/test_scheduled_refresh.py && git commit -m "feat: add verified scheduled refresh"`로 커밋한다.

### Task 4: GitHub Actions와 Streamlit 배포 설정

**Files:**
- Create: `.github/workflows/refresh-data.yml`
- Create: `.streamlit/config.toml`
- Modify: `.gitignore`
- Modify: `requirements.txt`
- Test: `tests/test_web_deploy_config.py`

**Interfaces:**
- Consumes: GitHub Actions secrets와 수동/예약 실행
- Produces: 매일 23:30 UTC 실행, 검증된 `share_snapshot.sqlite`, Streamlit 실행 설정

- [ ] workflow에 schedule·workflow_dispatch·secret 환경변수·검증 명령이 있는지 검사하는 테스트를 작성한다.
- [ ] `python -m pytest tests/test_web_deploy_config.py -q`로 실패를 확인한다.
- [ ] 한국시간 오전 8시 30분에 실행하고 실패 시 커밋하지 않는 workflow를 작성한다.
- [ ] 원본 DB·실제 secrets·임시 DB 제외 규칙과 headless 설정을 작성한다.
- [ ] 테스트 통과 후 `git add .github .streamlit/config.toml .gitignore requirements.txt tests/test_web_deploy_config.py && git commit -m "feat: configure scheduled web deployment"`로 커밋한다.

### Task 5: 윈도우 최초 준비와 사용자 매뉴얼

**Files:**
- Create: `PREPARE_WEB_DEPLOY.bat`
- Create: `README_WEB_DEPLOY.md`
- Test: `tests/test_web_deploy_docs.py`

**Interfaces:**
- Consumes: 사용자 PC의 `data/investment_advisor.sqlite`
- Produces: 검증된 `data/share_snapshot.sqlite`와 배포 ZIP

- [ ] 배치파일이 원본 DB 존재·Mart 생성·검증·API 키 제외를 수행하는지 검사하는 테스트를 작성한다.
- [ ] `python -m pytest tests/test_web_deploy_docs.py -q`로 실패를 확인한다.
- [ ] 더블클릭 가능한 준비 배치파일과 GitHub·Streamlit 설정 절차를 한글로 작성한다.
- [ ] 전체 테스트와 비밀정보 스캔을 실행한다.
- [ ] `git add PREPARE_WEB_DEPLOY.bat README_WEB_DEPLOY.md tests/test_web_deploy_docs.py && git commit -m "docs: add Windows web deployment handoff"`로 커밋한다.

### Task 6: 배포 산출물 검증

**Files:**
- Create: `investment_advisor_WEB_READY.zip`

**Interfaces:**
- Consumes: 커밋된 배포 프로젝트
- Produces: API 키·원본 DB가 없는 검증된 배포 ZIP

- [ ] `python -m pytest -q`로 전체 테스트를 실행한다.
- [ ] `python validate_snapshot.py data/share_snapshot.sqlite`로 공유 DB를 검사한다. 로컬에 DB가 없으면 사용자 PC 단계로 명확히 표시한다.
- [ ] `rg -n "KOSIS_API_KEY\s*=\s*[^\"']|CUSTOMS_SERVICE_KEY\s*=\s*[^\"']"`로 비밀정보 포함 여부를 검사한다.
- [ ] ZIP 무결성과 제외 파일 목록을 검사한다.
- [ ] 최종 커밋 SHA와 사용자가 수행할 세 단계—공유 DB 생성, GitHub secrets 등록, Streamlit 연결—를 인계한다.
