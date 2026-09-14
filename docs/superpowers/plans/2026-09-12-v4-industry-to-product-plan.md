# v4 Industry-to-Product Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cross-platform, fast, shareable top-down industry-to-product Streamlit dashboard before QuantiWise integration.

**Architecture:** Preserve the raw local data layer but introduce a compact SQLite mart that pre-aggregates Top20, research middle category, representative product, country exposure and KOSIS cycle signals. The UI reads marts only for normal browsing, and a share snapshot contains those marts without raw data or secrets.

**Tech Stack:** Python 3.11+, Streamlit, pandas, numpy, Plotly, SQLite.

**Spec:** `docs/superpowers/specs/2026-09-12-v4-industry-to-product-design.md`

## Global Constraints
- macOS and Windows local launch scripts must be included.
- Distribution ZIP must not include real API secrets.
- One compact CSV download per chart.
- Normal page browsing must not scan the multi-million-row raw Customs table.
- Taxonomy hierarchy is Top20 → research middle category → representative product → HS10.
- QuantiWise/company earnings is out of scope.

---

### Task 1: Taxonomy adapter
- [ ] Add the new 8,178-row research taxonomy and an adapter that outputs the legacy columns plus research hierarchy fields.
- [ ] Add tests for uniqueness and hierarchy counts.

### Task 2: Mart builder
- [ ] Add failing tests for building export, product-country, KOSIS and industry-signal marts from a fixture SQLite DB/cache.
- [ ] Implement `mart_builder.py` and verify the tests.

### Task 3: Fast v4 UI
- [ ] Add tests for app structure, page names, mart-only query paths, chart download helper and drill-down labels.
- [ ] Implement Overview, Industry Scanner, Industry Detail, Growth Leaders, Product Monitor, Export Flash and Data/QC pages against the mart.
- [ ] Implement one compact CSV download per chart.

### Task 4: Portability and share snapshot
- [ ] Add macOS/Windows migration, mart-build and portable-export scripts.
- [ ] Add `share_app.py` and deploy documentation/configuration.
- [ ] Ensure real secrets are excluded from distribution.

### Task 5: Verification and packaging
- [ ] Run the full test suite.
- [ ] Compile all Python files.
- [ ] Validate taxonomy and sample mart build.
- [ ] Zip the final `investment_advisor_READY_v4` directory and verify ZIP integrity.
