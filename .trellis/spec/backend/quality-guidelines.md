# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

Standards below are extracted from real decisions made during M1/M2 development.
Validation commands: `.venv/bin/python -m ruff check app tests scripts`,
`pytest -m "not slow"` (unit), `pytest tests/api -m slow` (live-DB integration).

---

## Forbidden Patterns

- **passlib** — unmaintained and incompatible with bcrypt>=4.1 (`__about__` removed,
  72-byte hard error). Use the `bcrypt` library directly via `app/core/security.py`
  (`hash_password` / `verify_password`). Decision recorded in docs/05 §2 (M2-4).
- **Plain-dict error bodies for coded errors** — endpoints that need an error `code`
  must raise `app.core.errors.ApiError(status, detail, code)`. Do not hand-build
  `{"detail": ..., "code": ...}` dicts or overload `HTTPException.detail` with dicts.
  Legacy endpoints raising plain `HTTPException` (detail-only) stay as-is.
- **`model_*` field names in pydantic-settings/BaseModel** — collides with pydantic v2
  protected namespaces (e.g. use `ml_model_dir`, not `model_dir`; or set
  `model_config = {"protected_namespaces": ()}` as in `app/schemas/predict.py`).

## Required Patterns

- **Cache-aside with post-cache slicing**: cache the full result under a key without
  pagination/window params; slice `page`/`months` after cache read
  (see `app/api/v1/analytics.py`). TTL constants live at module top.
- **Auth dependencies**: protect endpoints with `Depends(require_user)` /
  `Depends(require_admin)` from `app/api/deps.py`; never parse tokens inline.
- **ML feature hygiene**: all lag/rolling/pct features must be built from `shift`-ed
  history only (no current-month leakage) so training rows and inference rows are
  constructed by the same helper (`app/ml/features.py::_feature_row`).
- **Active-model pointer**: prediction endpoints load models via
  `ModelStore.load_active()` (pointer in `models/active.json`, admin-switchable via
  `PUT /admin/predict/models/active`); missing/stale pointer falls back to latest
  `random_forest`. New algorithms register in `app/ml/train.py::ALGORITHMS` and must
  set `ci_strategy`/`resid_std` in meta so `rolling_predict` can build intervals.
- **Ingestion cache invalidation**: `PipelineRunner` clears stale API caches after
  every run via `app.core.cache.invalidate_api_caches` (redis defaults to the global
  `redis_client`, so callers need not pass one). Any NEW `api:*` cache key family
  MUST be added to `_api_cache_patterns` in `app/core/cache.py`, or it will serve
  stale data for up to its TTL after ingestion.

## Testing Requirements

- Live-DB/network tests carry `pytest.mark.slow`; default run excludes them.
- API tests use registered temp users via `tests/api/conftest.py::auth_headers` /
  `admin_headers` fixtures; test users must clean up after themselves (`_delete_users`).
- **Test emails must use `example.com`** — email-validator rejects reserved TLDs
  like `.local` (422 on register).
- Tests that seed data by calling pipeline loaders directly (bypassing
  `PipelineRunner`) must still delete the relevant `api:*` Redis keys themselves —
  loaders never touch Redis; invalidation happens at the runner level.
- **Live-DB tests must purge their own rows** — register every fixture city code in
  the module's `TEST_CITY_CODES` list and purge before AND after the module (see
  `tests/pipeline/test_loaders.py::cleanup_test_rows`). Leaked fixture rows surface
  in user-facing pages (happened: 快照市/幂等市 showed up on the rank page).
