# M3-3 测试与加固

## Goal

按 docs/08 M3-3 交付：Playwright E2E 端到端测试、后端错误处理与日志加固、关键路径单元测试覆盖率 ≥ 70%、压测脚本与基线数据。

## Requirements

### 后端加固

- 全局兜底异常 handler：未捕获异常 → 500 `{"detail":"服务器内部错误","code":"INTERNAL_ERROR"}` 并 `logger.exception` 记录堆栈（不向客户端泄露内部信息）。
- 统一日志配置 `app/core/logging.py`：时间/级别/模块名格式，级别由 `settings.log_level`（默认 INFO）控制，启动时初始化。
- 请求访问日志中间件：method、path、状态码、耗时 ms（/health 除外）。

### 覆盖率 ≥ 70%（pytest -m "not slow" --cov=app）

- 现状 69%：补 `core/security`（哈希/JWT 往返、过期、篡改）、`collector/http_client`（重试/退避/UA，mock Session 不走网络）、错误 handler 单测。

### Playwright E2E（frontend/e2e）

- `@playwright/test` + chromium；`npm run test:e2e`；依赖本地 dev 环境（backend:8000 + vite:5173，reuseExistingServer）。
- 用例：游客首页搜索出图、受保护路由跳登录、admin 登录→大屏四面板渲染与联动（点柱状图切区域）、排行榜表格有数据、登出。

### 压测

- `backend/scripts/loadtest.py`（httpx asyncio）：可配并发/时长/端点，输出 总请求数/RPS/p50/p95/错误数；对 /health、/api/v1/cities、/api/v1/rank 跑基线并把结果记入 implement.md。

## 约束

- E2E 依赖真实 dev 数据（泉州），不在 CI 无数据环境跑；单测不新增任何网络/DB 依赖。
- 不引入 locust 等新压测框架，脚本用现有 httpx。

## Acceptance Criteria

- [x] 人为抛错的端点返回 500 JSON（含 code），日志有堆栈；访问日志含耗时
- [x] pytest -m "not slow" --cov=app 总覆盖率 ≥ 70%，全绿
- [x] npm run test:e2e 全绿（本地 dev 环境）
- [x] loadtest.py 跑出基线数据并记录
