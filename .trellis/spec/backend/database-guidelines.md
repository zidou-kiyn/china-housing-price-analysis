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

Real contracts from the multi-source collection work (2026-07). Code: `app/pipeline/loaders.py`, `app/services/nationwide_import.py`, `app/collector/sources/listing_annual.py`.

- `price_snapshot` upserts on constraint `uq_price_snapshot_region_month` (`region_type, region_id, year_month`). **Last write wins**, and the `source` column records the last writer. Re-running any import is idempotent.
- Registered source tags so far: `creprice` (monthly listing/appraised), `kaggle_lianjia` (Beijing monthly transaction), `listing_annual_58` / `listing_annual_anjuke` (nationwide annual listing average).
- **Annual data convention**: annual values land on `year_month = "YYYY-12"`, `supply_price` = listing average (¥/㎡), `sample_count = NULL`. Frontend labels these via `TrendPoint.source` (see `TrendLine.vue` SOURCE_LABELS) because listing prices run higher than transaction prices — never mix the two silently.
- Name-keyed bulk imports (58/anjuke CSVs) match `city.name` exactly and **skip unmatched names** (county-level cities, leagues, HK) instead of inserting new city rows; skipped names must be returned/logged.
- After any bulk snapshot write, invalidate API caches via `app/core/cache.py::invalidate_api_caches`. New `api:*` cache keys MUST be added to `_api_cache_patterns` there, or stale data will be served for up to the TTL.

---

## Common Mistakes

<!-- Database-related mistakes your team has made -->

(To be filled by the team)
