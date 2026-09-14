# v4.1 Changes

- `Industry Score` → **Fundamental Score**로 명칭/산식 개편.
- 수출 모멘텀 30% / 재고순환 25% / 실물활동 20% / 중분류 Breadth 15% / 6M Persistence 10%.
- 수출 YoY와 재고순환 동반 음수 시 50점 상한.
- Breadth 30% 미만 감점, 수출·재고순환 동시 둔화 추가 감점.
- Scanner에 구성점수, Breadth, Persistence, 판정 사유 표출.
- 점수는 주가/EPS/수급을 포함하지 않는 산업 fundamental screening임을 UI에 명시.
- 기존 v4 로컬 데이터를 바로 이어받는 `MIGRATE_FROM_V4.command/.bat` 추가.
- 현재 compact mart를 회사 공유용 ZIP으로 만드는 `MAKE_COMPANY_ZIP.command/.bat` 추가.
