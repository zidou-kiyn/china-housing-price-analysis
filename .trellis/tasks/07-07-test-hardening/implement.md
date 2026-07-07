# M3-3 执行计划

1. [x] app/core/logging.py + settings.log_level + main.py 接线（日志初始化、访问日志中间件、兜底 handler 在 errors.py）
2. [x] tests/core/test_security.py、tests/collector/test_http_client.py、tests/api/test_errors.py（不联网/不联库）
3. [x] 覆盖率验证 ≥ 70%，ruff
4. [x] 提交（后端加固部分）
5. [x] frontend: @playwright/test + playwright.config.ts + e2e 用例 + npm script
6. [x] E2E 本地跑绿
7. [x] backend/scripts/loadtest.py + 基线数据记录
8. [x] 提交（E2E + 压测部分）、finish

## 验证命令

```bash
cd backend && .venv/bin/python -m pytest -m "not slow" -q --cov=app && .venv/bin/python -m ruff check app tests scripts
cd frontend && npm run test:e2e
cd backend && .venv/bin/python scripts/loadtest.py --duration 15 --concurrency 20
```

## 压测基线（2026-07-07，dev 单进程 uvicorn，本机）

| endpoint | 并发 | RPS | p50 | p95 | err |
|---|---|---|---|---|---|
| /health | 20 | 343 | 11.1ms | 58.7ms | 0 |
| /api/v1/cities | 20 | 343 | 13.3ms | 63.4ms | 0 |
| /api/v1/rank（qz 区县） | 20 | 342 | 10.1ms | 57.4ms | 0 |

整体 1028 RPS / 15433 请求 0 错误。E2E：6 用例全绿（guest×3、auth×1、dashboard×2）。
