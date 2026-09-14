# Dashboard UX & Performance v3.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver a faster, denser v3.2 dashboard with lazy page execution, calendar period controls, unified 억달러 units, and research-terminal grid layouts.

**Architecture:** Introduce testable UI/data helpers in `dashboard_utils.py`, persistent KOSIS caching in `kosis_cache.py`, and refactor `app.py` to render exactly one selected page per rerun. Local SQLite/cached files are the boot source; network refresh is explicit and page-scoped.

**Tech Stack:** Python 3.11+, Streamlit >=1.40, pandas, numpy, Plotly, SQLite, requests.

**Spec:** `docs/superpowers/specs/2026-09-11-dashboard-ux-performance-design.md`

## Global Constraints
- Trade values display in 억달러 only.
- Period selection is month-normalized and shared across pages.
- No Customs/KOSIS network call on ordinary Overview boot.
- Preserve v3.1 SQLite schema and secrets format.
- Only selected page performs heavy page-specific queries.

---

### Task 1: Testable dashboard helpers
**Files:** Create `dashboard_utils.py`; Create `tests/test_dashboard_utils.py`.
**Interfaces:** `normalize_month_range`, `quick_month_range`, `filter_month_range`, `usd_to_100m`, `format_100m_usd`.
- [x] Write failing tests for month normalization, quick ranges, filtering, and unit conversion.
- [x] Run the helper test file and confirm RED.
- [x] Implement the five helpers.
- [x] Re-run helper tests and confirm GREEN.

### Task 2: Persistent KOSIS cache
**Files:** Create `kosis_cache.py`; Create `tests/test_kosis_cache.py`.
**Interfaces:** `read_kosis_cache(path)`, `write_kosis_cache(df, path)`, `cache_status(path)`.
- [x] Write failing round-trip/status tests.
- [x] Run and confirm RED.
- [x] Implement CSV cache helpers with date-safe strings.
- [x] Re-run and confirm GREEN.

### Task 3: Lazy application shell and refresh controls
**Files:** Modify `app.py`; Modify `tests/test_app_presentation.py`.
**Interfaces:** horizontal page radio; global period controls; local-first cached query wrappers; explicit refresh controls.
- [x] Add presentation tests that forbid `st.tabs` and require page selection, global calendar controls, and v3.2 title.
- [x] Run presentation tests and confirm RED.
- [x] Refactor app shell so no network calls occur before selected-page dispatch.
- [x] Add DB mtime keyed `st.cache_data` wrappers.
- [x] Re-run presentation and existing tests.

### Task 4: Dense grid pages and unified units
**Files:** Modify `app.py`; optionally extend `dashboard_utils.py` tests.
**Interfaces:** four KPI cards + two-column chart grids; all trade labels in 억달러.
- [x] Add source assertions for four-column KPI/grid conventions and no `$B`/`$M` labels in user-facing trade charts.
- [x] Run and confirm RED.
- [x] Rebuild Overview, Chartbook, Flash, Growth Leaders, Mapping Flow layouts.
- [x] Apply global month range to chart data.
- [x] Re-run tests.

### Task 5: KOSIS page-scoped loading and migration/start scripts
**Files:** Modify `app.py`, `README.md`; Create `MIGRATE_FROM_V3_1.command`.
**Interfaces:** cached KOSIS load by default on KOSIS pages; explicit KOSIS refresh; v3.1 SQLite migration.
- [x] Add script/documentation assertions.
- [x] Implement migration and KOSIS cache flow.
- [x] Run all tests and Python compilation.
- [x] Zip project and verify archive integrity.
