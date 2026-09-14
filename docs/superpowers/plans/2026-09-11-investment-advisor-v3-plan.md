# Investment Advisor v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a new ZIP with long-history Customs backfill, chartbook, cycle trajectory, mapping coverage waterfall, growth leaders, flash checkpoints, and full HS10 display labels.

**Architecture:** Keep `customs_pipeline.py` as API/persistence backbone; add focused `export_analytics.py`, `flash_trade.py`, and `hsk_labels.py`; keep `app.py` as orchestration/presentation. Network-specific behavior is cache-backed and calculations are tested offline.

**Tech Stack:** Python 3.11+, Streamlit, pandas, numpy, Plotly, requests, SQLite.

**Spec:** `docs/superpowers/specs/2026-09-11-investment-advisor-v3-design.md`

## Global Constraints
- Fixed reporting taxonomy: 2026 HSK10↔MTI↔MOTIR Top20.
- Never infer missing flash daily values.
- Default monthly history floor: 1988-01, configurable.
- Item×country history remains separately bounded.
- Preserve official HS names alongside polished names.

---

### Task 1: Historical backfill and coverage QC
**Files:** `customs_pipeline.py`, `tests/test_customs_pipeline_v3.py`
**Produces:** `parse_history_start`, `query_mapping_coverage_monthly`, `query_unmapped_hsk`, history-aware refresh.

### Task 2: Analytics calculations
**Files:** `export_analytics.py`, `tests/test_export_analytics.py`
**Produces:** `build_chartbook`, `growth_leaders`, `cycle_trajectory`, `mapping_waterfall`.

### Task 3: HS10 labels
**Files:** `hsk_labels.py`, `data/hsk10_display_labels_2026.csv`, `tests/test_hsk_labels.py`.

### Task 4: Flash checkpoints
**Files:** `flash_trade.py`, `data/export_flash_seed.csv`, `tests/test_flash_trade.py`.

### Task 5: Streamlit integration
**Files:** `app.py`, `.streamlit/secrets.toml.example`, `README.md`.

### Task 6: Verification and ZIP
Run full tests/compile and package without DB/venv/cache.
