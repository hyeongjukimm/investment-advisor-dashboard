# Investment Advisor 웹 공유 설정

## 결과

설정이 끝나면 동료는 `https://원하는이름.streamlit.app` 링크에서 프로그램 설치 없이 대시보드를 조회합니다. URL 접근 방식은 로그인 제한이 없으므로 링크가 재전달되면 다른 사람도 볼 수 있습니다.

## 1. 윈도우에서 최초 공유 데이터 만들기

이 웹 배포 폴더의 `data` 안에 기존 `investment_advisor.sqlite`, `kosis_cycle_cache.csv`, `export_flash_cache.csv`를 복사합니다. 실제 키 파일은 복사할 필요가 없습니다.

`PREPARE_WEB_DEPLOY.bat`을 실행합니다. 완료 후 다음 파일이 생깁니다.

- `data/share_snapshot.sqlite`: 웹이 읽을 경량 분석 DB
- `raw-state.zip`: 예약 갱신이 사용할 원본 DB 상태

## 2. GitHub 저장소 게시

1. GitHub Desktop에서 **File → New repository**를 선택합니다.
2. Local path로 이 폴더를 지정하고 저장소 이름을 `investment-advisor-dashboard`로 정합니다.
3. **Publish repository**를 누릅니다. URL 접속형 배포이므로 저장소를 Public으로 게시합니다.
4. `.gitignore` 때문에 원본 DB와 로컬 키는 게시되지 않고 `data/share_snapshot.sqlite`만 게시됩니다.
5. GitHub 웹의 **Releases → Draft a new release**에서 태그와 제목을 모두 `data-state`로 입력합니다.
6. `raw-state.zip`을 첨부하고 Release를 게시합니다.

## 3. 자동갱신 API 키 등록

GitHub 저장소에서 **Settings → Secrets and variables → Actions → New repository secret**으로 이동해 다음 두 항목을 등록합니다.

- `KOSIS_API_KEY`: KOSIS API 키
- `CUSTOMS_SERVICE_KEY`: 관세청 API 키

키 내용은 코드, 이 문서, 커밋에 입력하지 않습니다. Actions 로그에서도 키가 출력되지 않습니다.

**Actions → 최신 데이터 갱신 → Run workflow**를 한 번 수동 실행합니다. 초록색 체크가 표시되면 매일 한국시간 오전 8시 30분 자동갱신이 준비된 것입니다. 실패하면 기존 `share_snapshot.sqlite`는 유지됩니다.

## 4. Streamlit 링크 만들기

1. [Streamlit Community Cloud](https://share.streamlit.io/)에 GitHub 계정으로 로그인합니다.
2. **Create app**에서 위 저장소와 `main` 브랜치를 선택합니다.
3. Main file path에 `app.py`를 입력합니다.
4. Advanced settings의 Secrets에 아래 한 줄만 입력합니다.

```toml
SHARED_MODE = true
```

5. 원하는 URL 이름을 정하고 Deploy를 누릅니다.

웹 앱에는 KOSIS API Key와 관세청 API Key를 넣지 않습니다. API 갱신은 GitHub Actions만 수행하고 웹 앱은 `share_snapshot.sqlite`를 읽기만 합니다.

## 5. 동료에게 공유

배포가 끝나면 발급된 `https://....streamlit.app` 주소만 전달합니다. 동료는 Python, SQLite, API 키가 필요 없습니다.

## 운영 점검

- GitHub Actions가 초록색인지 확인
- 앱 사이드바의 수출 기준월과 Mart 생성시각 확인
- `data/refresh_status.json`에서 최근 성공시각 확인
- 갱신 실패 시 Actions 로그의 KOSIS `err/errMsg` 또는 관세청 오류 확인

## 복구

자동갱신이 실패해도 마지막 정상 공유 DB는 계속 제공됩니다. 원본 상태가 손상되면 로컬의 정상 `investment_advisor.sqlite`로 `PREPARE_WEB_DEPLOY.bat`을 다시 실행하고 `data-state` Release의 `raw-state.zip`을 교체합니다.
