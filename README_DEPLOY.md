# v4.1 Share / Deploy

## 가장 쉬운 중간 공유
1. Local v4.1에서 `MAKE_COMPANY_ZIP.command` 실행.
2. 생성된 `investment_advisor_v4.1_COMPANY_*.zip`을 Telegram/Drive로 전달.
3. 받는 사람은 압축 해제 후 macOS `START_MAC.command`, Windows `START_WINDOWS.bat` 실행.

## 고정 웹 링크로 공유
Portable ZIP의 내용(특히 `data/share_snapshot.sqlite`)을 **private GitHub repo**에 올리고 Streamlit Community Cloud에서 `app.py`를 entrypoint로 배포합니다.
- raw DB와 `.streamlit/secrets.toml`은 올리지 않습니다.
- snapshot만 사용하므로 공개 API 키가 필요 없습니다.
- 새 데이터로 갱신할 때 Local v4.1에서 Mart/Company ZIP을 다시 만든 뒤 `share_snapshot.sqlite`만 교체해 push하면 동일 URL이 업데이트됩니다.

회사 내부 데이터/QuantiWise가 추가되면 반드시 private repo/private app 또는 회사 승인 환경을 사용하세요.
