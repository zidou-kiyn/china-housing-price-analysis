# M3-3 执行计划

1. [ ] app/core/logging.py + settings.log_level + main.py 接线（日志初始化、访问日志中间件、兜底 handler 在 errors.py）
2. [ ] tests/core/test_security.py、tests/collector/test_http_client.py、tests/api/test_errors.py（不联网/不联库）
3. [ ] 覆盖率验证 ≥ 70%，ruff
4. [ ] 提交（后端加固部分）
5. [ ] frontend: @playwright/test + playwright.config.ts + e2e 用例 + npm script
6. [ ] E2E 本地跑绿
7. [ ] backend/scripts/loadtest.py + 基线数据记录
8. [ ] 提交（E2E + 压测部分）、finish

## 验证命令

```bash
cd backend && .venv/bin/python -m pytest -m "not slow" -q --cov=app && .venv/bin/python -m ruff check app tests scripts
cd frontend && npm run test:e2e
cd backend && .venv/bin/python scripts/loadtest.py --duration 15 --concurrency 20
```
