# v4 Industry-to-Product Design

## Goal
Turn the existing export/KOSIS dashboard into a fast top-down industry selector that can be used locally on macOS/Windows and packaged into a compact read-only snapshot for sharing/deployment before QuantiWise is connected.

## Scope
- Keep Customs raw history and KOSIS cache as source data in the local build.
- Build compact pre-aggregated marts so normal page loads do not group millions of raw rows.
- Use the 2026 fixed taxonomy with Top20 → research middle category → representative product → HS10 lineage.
- Combine export momentum with KOSIS production/shipment/inventory cycle into an Industry Scanner.
- Provide click drill-down in Growth Leaders from Top20 to middle category to representative product.
- Provide a Product Monitor with product export history and available tracked-country exposure.
- Keep Export Flash and Mapping/QC as supporting pages.
- Provide exactly one compact CSV download action per chart.
- Provide scripts to migrate local state from v3.2, build marts, create a compact portable/share snapshot, and run on macOS/Windows.
- Distribution ZIP must not contain real API secrets.

## Non-goals
- EPS/consensus/valuation/ranking from QuantiWise.
- Automated company exposure mapping beyond an empty/template interface.
- Claiming precise company attribution from HS codes alone.

## Data architecture
Local build:
- data/investment_advisor.sqlite: raw Customs database (optional but recommended)
- data/kosis_cycle_cache.csv: KOSIS cache
- data/investment_mart.sqlite: compact analysis mart generated from raw/cache

Share/portable build:
- data/share_snapshot.sqlite: compact mart-only snapshot. No raw Customs history and no API keys required for viewing.

Mart tables:
- mart_export_top20_monthly
- mart_export_middle_monthly
- mart_export_product_monthly
- mart_product_country_monthly
- mart_kosis_cycle_monthly
- mart_industry_signal_monthly
- dim_product_taxonomy
- mart_metadata

## Industry scoring
At each latest month with KOSIS data available, score each linked Top20 item from percentile ranks:
- export YoY 35%
- inventory cycle 30%
- shipment YoY 20%
- production YoY 15%
The score is a screening rank, not an expected-return forecast.

## Sharing
The source ZIP is cross-platform but does not contain the user's raw database/secrets. On the Mac with the existing v3.2 state, MIGRATE_FROM_V3_2 + BUILD_MARTS creates the local v4 state. MAKE_PORTABLE then creates a second portable ZIP containing only app code + share_snapshot.sqlite, safe to send to another machine for read-only viewing. The same share snapshot can be committed to a private GitHub repository and used by Streamlit Community Cloud.
