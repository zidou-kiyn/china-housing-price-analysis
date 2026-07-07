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

## Testing Requirements

- Live-DB/network tests carry `pytest.mark.slow`; default run excludes them.
- API tests use registered temp users via `tests/api/conftest.py::auth_headers` /
  `admin_headers` fixtures; test users must clean up after themselves (`_delete_users`).
- **Test emails must use `example.com`** — email-validator rejects reserved TLDs
  like `.local` (422 on register).
- Tests that read city/district lists should delete the relevant `api:*` Redis key
  first: loaders do NOT invalidate metadata caches yet (known issue, see below).

## Known Issues

- **Stale metadata caches**: pipeline loaders write city/district rows but do not
  invalidate `api:cities` / `api:districts:{code}` / `api:overview:*` Redis keys
  (TTL up to 1h). Candidate fix in M3 (invalidate-on-load).
