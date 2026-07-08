# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

<!--
Document your project's database conventions here.

Questions to answer:
- What ORM/query library do you use?
- How are migrations managed?
- What are the naming conventions for tables/columns?
- How do you handle transactions?
-->

(To be filled by the team)

---

## Query Patterns

<!-- How should queries be written? Batch operations? -->

(To be filled by the team)

---

## Migrations

<!-- How to create and run migrations -->

(To be filled by the team)

---

## Naming Conventions

<!-- Table names, column names, index names -->

(To be filled by the team)

---

## PriceSnapshot Source & Granularity Conventions

Real contracts from the multi-source collection work (2026-07, updated after source-isolation). Code: `app/pipeline/loaders.py`, `app/core/source_policy.py`, `app/services/price_select.py`, `app/services/nationwide_import.py`.

- **Source-independent storage** (migration 005): unique constraint is `uq_price_snapshot_region_month_source` (`region_type, region_id, year_month, source`), `source` is NOT NULL. Each source keeps its own full series; writes NEVER overwrite another source's rows. Re-running any import stays idempotent within its own source. (History: the old region+month key let the 58 annual import silently overwrite Beijing's kaggle transaction Decembers — that class of bug is now structurally impossible.)
- **Merge happens at READ time, in one place**: `app/services/price_select.py::select_merged_snapshots` picks one row per (region, month) via `app/core/source_policy.py::SOURCE_PRIORITY` (monthly sources beat annual listing: creprice > kaggle_lianjia > listing_annual_58 > listing_annual_anjuke). All single-value readers (default `/prices/trend`, analytics rank/compare/mapheat, ML `_load_snapshot_rows`) MUST go through it — a naive `dict[year_month] = snap` grouping silently picks a random source.
- **New data sources MUST register in `SOURCE_PRIORITY` and `SOURCE_META`** (granularity monthly|annual, basis listing|transaction), or they fall to priority 9 and get default 口径 metadata.
- Per-source display: `GET /prices/trend/series` returns one series per source; the frontend draws monthly sources as solid lines and annual as dashed+symbols and never connects across sources (`TrendLine.vue` split mode).
- **Annual data convention**: annual values land on `year_month = "YYYY-12"`, `supply_price` = listing average (¥/㎡), `sample_count = NULL`. Listing prices run higher than transaction prices — annual-sourced values must carry a「年度·挂牌」label wherever shown (rank tag, compare tooltip, trend legend).
- Name-keyed bulk imports (58/anjuke CSVs) match `city.name` exactly and **skip unmatched names** (county-level cities, leagues, HK) instead of inserting new city rows; skipped names must be returned/logged.
- After any bulk snapshot write, invalidate API caches via `app/core/cache.py::invalidate_api_caches`. New `api:*` cache keys MUST be added to `_api_cache_patterns` there, or stale data will be served for up to the TTL.
- Tests that write real cities into the dev DB must register their city codes in `TEST_CITY_CODES` (`tests/pipeline/test_loaders.py`) — unregistered fixtures leak into the frontend rank list (happened twice: 快照市, 共存市).

### ML training-data path (2026-07, ml-dataset-builder)

- **ML training reads are per-source, NOT merged**: training goes through `app/services/price_select.py::select_source_snapshots` → `app/ml/dataset.py::build_multi_source_series`. Do NOT feed `select_merged_snapshots` output into training — merged series splice listing/transaction/annual points into one sequence with no口径 features.
- The dataset builder classifies sources via `SOURCE_META` granularity/basis only; hardcoding source-name lists in `app/ml/` is forbidden (unregistered sources fall back to monthly/listing defaults).
- **Listing→transaction calibration is a per-year ratio curve** (estimated from overlapping (region, month) pairs, median per year; nearest-year outside the overlap range). A single global coefficient is wrong — Beijing's overlap ratio drifts 0.79→1.09 across 2010–2017. The curve used at training time is stored in the model's `meta["dataset"]["ratio_curve"]`; inference-side series construction must reuse that stored curve, never re-estimate.
- Annual-interpolated samples carry `is_annual_interp=1` and sample weight `ANNUAL_SAMPLE_WEIGHT` (0.3); real monthly points always win over annual-interpolated values for the same (region, month).

---

## Common Mistakes

<!-- Database-related mistakes your team has made -->

(To be filled by the team)
