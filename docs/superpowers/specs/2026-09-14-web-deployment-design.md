# Investment Advisor 웹 배포 설계

## 목표

동료가 Python이나 데이터베이스를 설치하지 않고 하나의 URL로 대시보드를 조회한다. KOSIS·관세청 데이터는 예약 작업으로 갱신하며 API 키와 원본 DB는 웹 화면과 소스 저장소에 노출하지 않는다.

## 공개 범위

- 접근 방식: URL을 아는 사람이 로그인 없이 접속
- 보안 성격: 비공개 링크가 아니라 사실상 공개 URL
- 금지 데이터: 개인 API 키, `.streamlit/secrets.toml`, 회사 내부 자료, 사용자 PC 경로
- 공개 가능 데이터: 공공 API 기반 집계값과 공유용 분석 Mart

## 권장 구조

1. GitHub 저장소에는 앱 코드, 테스트, 분류표, 배포 설정만 둔다.
2. 원본 `investment_advisor.sqlite`는 저장소에 커밋하지 않는다.
3. 사용자 PC에서 최초 1회 `share_snapshot.sqlite`를 생성한다.
4. Streamlit 웹 앱은 읽기 전용 `share_snapshot.sqlite`만 조회한다.
5. GitHub Actions 예약 작업은 KOSIS·관세청 데이터를 갱신하고 새 공유 Mart를 만든다.
6. 갱신 성공 시에만 기존 공유 Mart를 교체한다. 실패 시 마지막 정상본을 유지한다.
7. 웹 화면에는 데이터 기준월, Mart 생성시각, 최근 갱신 성공시각을 표시한다.

## 데이터 갱신

- 기본 주기: 한국시간 매일 오전 8시 30분
- 수동 실행: GitHub Actions의 수동 실행 버튼 제공
- KOSIS: 12개월 청크, 오류 30(자료 없음) 구간 건너뛰기, 기존 캐시와 병합
- 관세청: 공개된 최신 기준월만 증분 적재
- 최근 수출: 관세청 홈페이지의 공식 발표 시점 데이터만 저장
- 원자성: 임시 DB 생성 → 무결성 검사 → 행 수와 최신월 검사 → 정상일 때 교체
- 실패 처리: 기존 정상 DB 보존, 로그에 실제 `err`·`errMsg` 기록

## 웹 앱 동작

- 배포 모드에서는 API 키 입력란과 데이터 갱신 버튼을 숨긴다.
- 조회 사용자는 기간, 산업, 품목을 선택하고 CSV를 내려받을 수 있다.
- 모든 페이지는 공유 Mart만 읽는다.
- DB가 없거나 손상되면 빈 화면 대신 관리자용 진단 문구를 표시한다.
- 화면 하단에 공공데이터 출처와 마지막 갱신시각을 표시한다.

## 파일 구성

- `app.py`: 웹 UI와 읽기 전용 배포 모드
- `deployment_mode.py`: 로컬/배포 모드 판정과 관리자 기능 차단
- `scheduled_refresh.py`: KOSIS·관세청 증분 갱신과 Mart 생성
- `validate_snapshot.py`: 필수 테이블, 행 수, 최신월, 무결성 검사
- `.github/workflows/refresh-data.yml`: 예약·수동 갱신
- `.streamlit/config.toml`: 웹 배포 설정
- `.streamlit/secrets.toml.example`: 키 이름만 제공
- `data/share_snapshot.sqlite`: 최초 배포용 공유 Mart
- `requirements.txt`: 배포 의존성
- `README_WEB_DEPLOY.md`: 최초 배포와 복구 절차

## API 키 관리

- 실제 키는 GitHub Actions Secrets와 Streamlit 배포 설정에만 입력한다.
- 로그와 오류 메시지에서는 API 키를 마스킹한다.
- `.gitignore`에서 `.streamlit/secrets.toml`, 원본 DB, 임시 DB를 제외한다.

## 배포와 복구

- GitHub 저장소와 Streamlit 앱을 연결해 고정 URL을 발급한다.
- 코드 변경은 테스트 통과 후 배포한다.
- 새 데이터가 잘못되면 마지막 정상 `share_snapshot.sqlite`로 되돌린다.
- 예약 작업이 실패해도 웹 앱 자체는 마지막 정상 데이터로 계속 열린다.

## 검증 기준

- 로컬 모드의 기존 기능과 테스트가 유지된다.
- 배포 모드에서 API 키와 갱신 버튼이 보이지 않는다.
- API 키 문자열이 저장소 및 생성 ZIP에 포함되지 않는다.
- 공유 Mart 필수 테이블과 최신월 검사가 통과한다.
- 두 명 이상의 동시 조회에서 SQLite 쓰기 충돌이 발생하지 않는다.
- 예약 갱신 실패 시 기존 대시보드가 계속 조회된다.

## 최초 배포 전 사용자 입력

- 사용자 윈도우 PC의 최신 `investment_advisor.sqlite`
- KOSIS 및 관세청 API 키를 배포 설정에 직접 입력
- 사용할 GitHub 저장소 이름과 Streamlit URL 이름

