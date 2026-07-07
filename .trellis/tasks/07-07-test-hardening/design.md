# M3-3 技术设计

## 后端

- `app/core/logging.py::setup_logging(level)`：根 logger 加 StreamHandler，格式
  `%(asctime)s %(levelname)s %(name)s: %(message)s`；幂等（重复调用不叠加 handler）。
- `settings.log_level: str = "INFO"`。
- `main.py`：import 期调用 setup_logging；`@app.middleware("http")` 记录
  `method path -> status (耗时ms)`，path == /health 跳过。
- `errors.py::register_exception_handlers` 增加 `@app.exception_handler(Exception)`：
  logger.exception + 500 JSON `{"detail":"服务器内部错误","code":"INTERNAL_ERROR"}`。
  注意 CORSMiddleware 在外层，兜底响应仍带 CORS 头。

## 单测策略

- security：哈希验证往返、错 hash 返回 False、token 往返、过期（负 expire minutes monkeypatch）、
  篡改 secret 抛 JWTError。
- http_client：注入 fake Session（record 调用、可编程失败次数）+ delay/backoff 全 0，
  验证成功路径、N-1 次失败后成功、达上限抛最后异常、UA 头存在。
- errors：独立 FastAPI app + register_exception_handlers + 抛 RuntimeError/ApiError 的路由，
  httpx ASGITransport(raise_app_exceptions=False) 断言 500/JSON 与自定义 code。

## E2E

- `frontend/playwright.config.ts`：testDir e2e，baseURL http://localhost:5173，
  webServer `npm run dev`（reuseExistingServer: true），chromium 单浏览器。
- 用例文件：`e2e/guest.spec.ts`（首页搜索出图、/dashboard 302 登录）、
  `e2e/auth-dashboard.spec.ts`（admin 登录 → 大屏渲染/联动 → 登出）、
  `e2e/rank.spec.ts`（排行榜有行）。
- canvas 联动断言用 el-tag 文本变化（点击柱状图坐标经 bounding box 计算）。

## 压测

- `scripts/loadtest.py`：argparse（--base-url/--duration/--concurrency/--endpoints），
  asyncio worker 循环打点收集耗时，输出汇总表；退出码 0/1（有错误请求时 1）。
