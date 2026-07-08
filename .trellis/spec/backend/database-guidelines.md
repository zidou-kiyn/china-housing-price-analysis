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

Real contracts from the multi-source collection work (2026-07, updated after creprice-first source isolation, 07-08). Code: `app/pipeline/loaders.py`, `app/core/source_policy.py`, `app/services/price_select.py`, `app/services/nationwide_import.py`.

- **Source-independent storage** (migration 005): unique constraint is `uq_price_snapshot_region_month_source` (`region_type, region_id, year_month, source`), `source` is NOT NULL. Each source keeps its own full series; writes NEVER overwrite another source's rows. Re-running any import stays idempotent within its own source. (History: the old region+month key let the 58 annual import silently overwrite Beijing's kaggle transaction Decembers — that class of bug is now structurally impossible.)
- **Reads are single-source, hard-isolated** (creprice-first, 07-08): all single-value readers take a `source` query param (`app/api/deps.py::source_param`, default `creprice`, unregistered source → 422) and go through `app/services/price_select.py::select_snapshots_for_source` (one source, `WHERE source == :source`, NO cross-source merge). **There is no merge reader** — `select_merged_snapshots` / `source_policy.priority_case` were deleted (git history recoverable). `SOURCE_PRIORITY` now only orders the frontend source switcher and `/prices/trend/series` split lines; it no longer drives value selection. Rationale: cross-source merge produced phantom monthly data (e.g. Quanzhou's pre-2025-07 months were filled by 58 annual points *replacing* the real creprice series). NEVER re-introduce a merge path — `distribution` is creprice-only (its table has no `source` column; non-creprice → `[]`).
- **New data sources MUST register in `SOURCE_PRIORITY` and `SOURCE_META`** (granularity monthly|annual, basis listing|transaction), or they fall to priority 9 and get default 口径 metadata.
- Per-source display: `GET /prices/trend/series` returns one series per source; the frontend draws monthly sources as solid lines and annual as dashed+symbols and never connects across sources (`TrendLine.vue` split mode).
- **Annual data convention**: annual values land on `year_month = "YYYY-12"`, `supply_price` = listing average (¥/㎡), `sample_count = NULL`. Listing prices run higher than transaction prices — annual-sourced values must carry a「年度·挂牌」label wherever shown (rank tag, compare tooltip, trend legend).
- Name-keyed bulk imports (58/anjuke CSVs) match `city.name` exactly and **skip unmatched names** (county-level cities, leagues, HK) instead of inserting new city rows; skipped names must be returned/logged.
- After any bulk snapshot write, invalidate API caches via `app/core/cache.py::invalidate_api_caches`. New `api:*` cache keys MUST be added to `_api_cache_patterns` there, or stale data will be served for up to the TTL.
- Tests that write real cities into the dev DB must register their city codes in `TEST_CITY_CODES` (`tests/pipeline/test_loaders.py`) — unregistered fixtures leak into the frontend rank list (happened twice: 快照市, 共存市).

### ML training-data path (2026-07, ml-dataset-builder; creprice-first 07-08)

- **Training/predict source whitelist** (creprice-first, 07-08): `source_policy.TRAINING_SOURCES = ("creprice",)` + `training_rows_only(rows_by_source)` filter applied at the **load boundary** — `predictions.py::_load_source_rows` (training + predict) and `data_quality.py::_compute_data_fingerprint` (fingerprint口径 must match training) — NOT inside `build_multi_source_series` (the builder stays source-agnostic so its multi-source unit tests keep exercising the retained calibration/shaping paths). Non-whitelist sources (58/kaggle/anjuke) never reach training/predict; the calibration/expansion code is retained but unreachable (reversible — widen the whitelist to restore multi-source training). Consequence — **coverage collapse is intended**: annual-only cities are no longer predictable (no creprice history → 404), and formerly-mixed cities predict as `data_quality=monthly`. The audit sections (overlap/direction/coverage) do NOT apply the whitelist — they see all sources.
- **No-active-model empty window**: after the creprice-first model purge, `backend/models/` is empty and `predict` returns `ApiError(404, ..., "NO_ACTIVE_MODEL")`; the data-quality report degrades `model_freshness.status` to `"unknown"` (never 500). v1.8 retrain is gated on 07-07-full-data-crawl completion (separate task).
- **ML training reads are per-source, NOT merged**: training goes through `app/services/price_select.py::select_source_snapshots` → `app/ml/dataset.py::build_multi_source_series` (grouped by source, each source's full series preserved for calibration/expansion). There is no merged reader anymore (`select_merged_snapshots` was removed in the creprice-first change); a naive `dict[year_month] = snap` grouping across sources is forbidden — it silently splices listing/transaction/annual points into one sequence with no口径 features.
- The dataset builder classifies sources via `SOURCE_META` granularity/basis only; hardcoding source-name lists in `app/ml/` is forbidden (unregistered sources fall back to monthly/listing defaults).
- **Listing→transaction calibration is a per-year ratio curve** (estimated from overlapping (region, month) pairs, median per year; nearest-year outside the overlap range). A single global coefficient is wrong — Beijing's overlap ratio drifts 0.79→1.09 across 2010–2017. The curve used at training time is stored in the model's `meta["dataset"]["ratio_curve"]`; inference-side series construction must reuse that stored curve, never re-estimate.
- Annual-interpolated samples carry `is_annual_interp=1` and sample weight `ANNUAL_SAMPLE_WEIGHT` (0.3); real monthly points always win over annual-interpolated values for the same (region, month).
- **Model meta is append-only** (old pickles must keep loading/predicting): new meta fields get optional Pydantic fields (`None` default) in `ModelVersionOut`, and readers use chained `.get`. Since ml-train-eval, meta carries `baselines` (last_value/seasonal naive), `beats_baseline`, `per_region_metrics`, and stratified `metrics_real_monthly` — **quote `metrics_real_monthly`, not the headline `metrics`, when judging a model trained on annual-expanded data**: the full validation set is dominated by smoothed interpolated samples (e.g. 0.25% vs the honest 2.71% MAPE).
- **NBS index data lives in `price_index_snapshot`** (migration 006), never in
  `price_snapshot` — index values are floats with multiple口径 per (city, month)
  (dwelling_type new|second × base_type mom|yoy|fixed). Import via
  `services/index_import.py` (GitHub CSV, 70-city EN→CN static crosswalk, idempotent);
  the index source is NOT registered in `SOURCE_PRIORITY`/`SOURCE_META` (it is not a
  price_snapshot source). ML annual-to-monthly interpolation uses the second-hand
  mom index to shape segments between annual anchors (chain-relink + geometric
  drift correction, anchors preserved exactly; any missing month in a segment falls
  back to linear for that whole segment). `DatasetMeta.shaping` records
  `{nbs_index: n, linear: m}` city counts.
- **Predict path (`GET /predict`) uses the same builder as training** (ml-predict-coverage): `select_source_snapshots` → `build_multi_source_series` with `ratio_curve_override` from the active model's `meta["dataset"]["ratio_curve"]` (`{}` = trained-without-calibration → skip; missing key = pre-dataset-builder model → on-the-fly estimate, transitional). Response carries `data_quality` (monthly|annual_interp|mixed); `annual_interp` widens the CI by `ANNUAL_CI_PENALTY` (1.5). `prediction` table rows for other model_versions of the same (region, model_name) are deleted lazily in the same transaction as each new write — stale rows for never-re-predicted regions are expected, not a bug.

---

## Common Mistakes

<!-- Database-related mistakes your team has made -->

(To be filled by the team)
