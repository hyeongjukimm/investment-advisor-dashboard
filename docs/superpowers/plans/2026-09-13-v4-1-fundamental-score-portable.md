# v4.1 Fundamental Score & Portable Share Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the simplistic cross-sectional Industry Score with a transparent Fundamental Score and ship a v4.1 Mac/Windows package that can migrate v4 state and generate a self-contained company ZIP.

**Architecture:** Keep the existing mart-first pipeline. Add a deterministic scoring function that derives export momentum, inventory-cycle, real-activity, breadth, and persistence components from existing Top20/middle/KOSIS marts; write the component columns into `mart_industry_signal_monthly`; update Streamlit labels/tables to explain the score. Add v4→v4.1 migration and company-zip scripts that embed only the compact share snapshot, never raw DB or secrets.

**Tech Stack:** Python 3.11+, pandas, SQLite, Streamlit, Plotly, pytest, shell/batch launchers.

**Spec:** Conversation-approved v4.1 scope: Fundamental Score = Export Momentum 30%, Inventory Cycle 25%, Production/Shipment 20%, Breadth 15%, Persistence 10%; penalize narrow/weak recovery and cap jointly negative export+inventory-cycle cases; preserve Top20→middle→product drilldown; share on Mac/Windows.

## Global Constraints
- Preserve existing 1995+ raw data and 2026 taxonomy; do not redownload raw history.
- Never bundle real API secrets in a share/company ZIP.
- Company ZIP must run from `START_WINDOWS.bat` with an embedded compact snapshot.
- Score is a fundamental screening score, not expected return or stock-price score.
- Keep one compact CSV download control per chart.

---

### Task 1: Fundamental scoring engine
**Files:** Modify `mart_builder.py`; Test `tests/test_mart_builder_v4.py`.
**Interfaces:** `score_industry_fundamentals(signal, middle) -> DataFrame`; `build_industry_signal(..., middle=None) -> DataFrame`.
- [ ] Add failing tests for component columns, broad persistent improvement outranking one-month base-effect spikes, and negative export+inventory-cycle score cap.
- [ ] Run targeted tests and confirm failure for missing scoring function/columns.
- [ ] Implement component calculations and score gates.
- [ ] Run targeted and full tests.

### Task 2: Scanner presentation
**Files:** Modify `app.py`, `README.md`; Test `tests/test_app_v4_structure.py`.
**Interfaces:** Reads the new mart component columns; no new external service.
- [ ] Add failing structure tests for Fundamental Score naming and component fields.
- [ ] Update Overview, Industry Scanner, and Industry Detail labels/tables/hover details.
- [ ] Show score methodology and warnings that price/EPS/flow are not included yet.
- [ ] Run presentation/structure tests.

### Task 3: v4.1 portability
**Files:** Modify `make_portable.py`, launchers/readmes; Create `MIGRATE_FROM_V4.command/.bat`, `MAKE_COMPANY_ZIP.command/.bat`; Test `tests/test_start_scripts_v32.py` and new portability assertions.
**Interfaces:** v4 migration copies local raw DB, mart, KOSIS cache, flash cache, secrets; company packager embeds `share_snapshot.sqlite` only.
- [ ] Write failing tests for v4.1 script/version names and company ZIP behavior markers.
- [ ] Implement migration/share scripts and version naming.
- [ ] Run launcher tests.

### Task 4: Verification and release
**Files:** Release ZIP `/mnt/data/investment_advisor_READY_v4.1.zip`.
- [ ] Run `pytest -q`.
- [ ] Run `python -m py_compile` on production modules.
- [ ] Build a fixture mart and inspect score columns/gates.
- [ ] Validate shell scripts with `bash -n` and ZIP integrity with `unzip -t`.
- [ ] Package v4.1 without `.venv`, raw DB, local mart, or real secrets.
