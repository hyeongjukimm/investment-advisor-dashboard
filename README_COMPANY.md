# 회사 PC에서 확인하는 방법 · v4.1

## 권장 전달 방식
Mac의 v4.1 폴더에서 `MAKE_COMPANY_ZIP.command`를 실행합니다.
생성되는 `investment_advisor_v4.1_COMPANY_YYYYMMDD_HHMM.zip`을 Telegram/Drive로 회사 PC에 전달합니다.

이 Company ZIP에는 **현재 Mac의 compact analysis snapshot만** 들어갑니다.
- 포함: Industry/Product marts, Fundamental Score, taxonomy, app code
- 제외: 279만+ raw 관세청 DB, 실제 API key, `.streamlit/secrets.toml`

## Windows 실행
1. ZIP 압축 해제
2. `START_WINDOWS.bat` 더블클릭
3. 최초 1회 Python package 설치 후 브라우저에서 `http://localhost:8501` 확인

회사 네트워크가 pip 설치를 차단한다면 기존에 설치된 Python/Streamlit 환경 또는 사내 승인 환경이 필요합니다.

## Fundamental Score 주의
이 점수는 산업 실물·수출 screening용입니다. **주가·EPS·컨센서스 revision·외국인/기관 수급은 아직 포함하지 않습니다.**
