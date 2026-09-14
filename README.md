# Investment Advisor Tool · READY v4.1

**목적:** `실물경기(KOSIS) → 수출 → 산업 → 리서치중분류 → 대표품목`으로 내려가면서 Top-down 투자 아이디어를 찾는 Phase 1 build입니다. QuantiWise EPS/Revision/수급은 다음 Phase에서 붙입니다.

## v4.1 핵심
- **Mart-first:** 279만+ raw HS 행을 페이지 클릭 때마다 다시 집계하지 않습니다. `investment_mart.sqlite`를 사전 생성해 빠르게 읽습니다.
- **Overview 8 charts:** 수출 + KOSIS를 같은 화면에서 투자 판단용으로 결합합니다.
- **Industry Scanner / Fundamental Score:** 수출 모멘텀 30% + 재고순환 25% + 실물활동 20% + 중분류 Breadth 15% + 6M Persistence 10%. 수출·재고순환 동반 약세에는 50점 상한, Breadth<30%에는 감점을 적용합니다. **주가·EPS·수급은 아직 포함하지 않는 산업 fundamental screening 점수**입니다.
- **Growth Leaders:** Top20 막대 클릭 → 리서치중분류 → 대표품목.
- **Product Monitor:** 대표품목의 수출액/YoY/MoM/중량/단가 및 현재 저장된 추적국가 exposure.
- **한 차트 = CSV 1개:** 작고 우측 정렬된 CSV 버튼.
- **Portable/Share:** compact snapshot ZIP을 만들어 Mac/Windows에서 동일 화면을 볼 수 있습니다.

## Mac에서 현재 v4 데이터 바로 이어받기
기존 v4와 v4.1 폴더를 Desktop에 나란히 둔 뒤:
```bash
cd ~/Desktop/investment_advisor_READY_v4.1
xattr -dr com.apple.quarantine .
chmod +x *.command
./MIGRATE_FROM_V4.command
./START_MAC.command
```
기존 raw DB/KOSIS cache를 복사한 뒤 **v4.1 Fundamental Score로 mart만 재생성**합니다. 30년치 관세청 데이터를 다시 다운로드하지 않습니다.

## Mac에서 기존 v3.2 데이터 이어받기
v3.2와 v4.1 폴더를 Desktop에 나란히 둔 뒤:
```bash
cd ~/Desktop/investment_advisor_READY_v4.1
xattr -dr com.apple.quarantine .
chmod +x *.command
./MIGRATE_FROM_V3_2.command
./START_MAC.command
```
`MIGRATE_FROM_V3_2.command`는 기존 raw DB/KOSIS cache/로컬 secrets를 복사하고 v4.1 Mart를 생성합니다.

## Windows
Portable ZIP이면 `START_WINDOWS.bat`만 실행하면 됩니다. Local research build로 v3.2 state를 이어받으려면 v3.2와 v4.1 폴더를 같은 위치에 두고 `MIGRATE_FROM_V3_2.bat` 실행.

## Telegram/회사 PC로 보내기
Mac에서 v4.1이 정상 실행된 뒤:
```bash
./MAKE_COMPANY_ZIP.command
```
프로젝트 폴더에 `investment_advisor_v4.1_COMPANY_YYYYMMDD_HHMM.zip`이 생성됩니다. **그 ZIP을 Telegram으로 회사 PC에 보내면 됩니다.** 회사 PC에서는 압축을 풀고 `START_WINDOWS.bat`을 실행합니다. 회사 ZIP에는 현재 compact `share_snapshot.sqlite`가 들어가므로 raw DB/API key 없이 같은 분석 화면을 확인할 수 있습니다.

## 웹 링크 배포
`README_DEPLOY.md` 참고. Portable snapshot을 private GitHub + Streamlit Community Cloud에 올리면 고정 URL로 중간 결과를 공유할 수 있습니다.

## 데이터 파일
- `data/investment_advisor.sqlite`: Local raw Customs DB (배포 ZIP에는 없음)
- `data/kosis_cycle_cache.csv`: Local KOSIS cache
- `data/investment_mart.sqlite`: Local compact analysis mart
- `data/share_snapshot.sqlite`: Portable/share mart
- `data/motir20_hsk_mti_mapping_2026_full_clean.csv`: 2026 fixed research taxonomy (8,178 HS10 / 20 Top20 / 144 research middle / 439 representative products)

## 보안
배포 ZIP에는 real `.streamlit/secrets.toml`을 포함하지 않습니다. API key가 필요한 것은 Local Research mode뿐입니다.

Legacy alias: `./MAKE_PORTABLE.command` still works; v4.1 preferred command is `./MAKE_COMPANY_ZIP.command`.
