# Investment Advisor v3 Design

## Goal
Upgrade the existing Streamlit dashboard into a long-history, investor-facing export/industry analysis tool while keeping the 2026 MOTIR Top20 taxonomy as the stable reporting taxonomy.

## Data principles
- Monthly Customs HS10 item data: backfill from configurable `CUSTOMS_HISTORY_START` (default `1988-01`) through the latest API-observed complete month. Empty historical chunks are allowed; subsequent runs refresh recent revisions only.
- Country totals follow the same historical floor. Item×country stays bounded independently because it is an exposure view rather than the long-history backbone.
- 2026 HSK10→MTI→Top20 mapping is the fixed reporting taxonomy. Historical exact-code coverage is measured via mapped value, unmapped value, mapped ratio and category presence.
- Flash uses only official observation points (1–10, 1–20, month-end). No synthetic daily values.

## Surfaces
1. Export Chartbook: Top20 / middle-category, monthly exports, YoY, MoM, YTD, prior-year YTD, 3M average YoY.
2. Industry Cycle: production/shipment/inventory plus trajectory, latest bubble, selectable polynomial order 2–4.
3. Mapping Flow: hierarchy counts plus coverage waterfall and unmapped HS10 table.
4. Growth Leaders: Top20 or middle-category, selected period, growth, absolute increase, contribution, average YoY, latest YoY, minimum-base filter.
5. Export Flash: 10-day/20-day/month-end checkpoints, `집계중` badge, prior-year/prior-month/5-year comparison when observations exist.
6. HS10 label dictionary: preserve official name and generate contextual polished labels for all 8,178 mapping rows.

## UI
Overview / Industry Cycle / Export Chartbook / Export Flash / Growth Leaders / Mapping Flow / Data-QC.

## Reliability
- Network failures preserve existing DB/cache.
- Backfill range and status are visible.
- Existing tests remain passing; new calculations have offline unit tests.
