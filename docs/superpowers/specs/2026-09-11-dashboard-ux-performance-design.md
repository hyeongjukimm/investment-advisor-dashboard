# Dashboard UX & Performance v3.2 Design

## Goal
Make the dashboard feel like a dense research terminal rather than a long Streamlit demo while preserving all v3.1 analysis features.

## Navigation and execution
Replace eager `st.tabs` with a single horizontal page selector. Only the selected page executes its page-specific queries and network work. The default boot path reads only local SQLite metadata and the latest cached panel; it does not call KOSIS or Customs APIs.

## Data refresh
Customs refresh becomes explicit via a top/sidebar “최신 데이터 확인” action, with the last stored month visible at boot. KOSIS is fetched only on Industry Cycle or Cross Signal and persisted to `data/kosis_cycle_cache.csv`; subsequent page loads use the local cache until the user requests a refresh.

## Global period controls
Use a calendar-based start/end date picker and quick ranges (1Y, 3Y, 5Y, 10Y, 전체). Normalize selections to month starts and share them through `st.session_state`. Page charts filter to this range where meaningful.

## Units
All trade-value charts and metrics use 억달러 (`USD / 1e8`). Growth rates remain percent and cycle spreads remain percentage points. No mixed $M/$B/raw USD presentation.

## Layout
Use a four-column KPI row and two-column chart grid; each chart uses the full column width and consistent 340–430px heights. Dense pages should fit the main analytical view into roughly one laptop viewport plus one scroll rather than a long vertical chain.

## Pages
Preserve Overview, Industry Cycle, Export Chartbook, Export Flash, Growth Leaders, Mapping Flow, Cross Signal, and Data/QC. Chartbook and Growth Leaders receive the strongest grid redesign. Export Flash uses four KPIs and a 2x2 chart/table layout.

## Compatibility
Keep Python 3.11+, Streamlit >=1.40, current SQLite schema, v3.1 DB migration, 2026 fixed Top20 taxonomy, and current API credentials/secrets format.
