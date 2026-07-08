# 采集流程并发优化 — 实施计划

## 检查清单

### Part 1: 配置变更
- [ ] `backend/app/core/config.py`: 新增 `crawl_concurrency: int = 5`
- [ ] `backend/app/core/config.py`: `crawl_request_delay_min` 默认值改为 `0.3`
- [ ] `backend/app/core/config.py`: `crawl_request_delay_max` 默认值改为 `0.8`
- [ ] `.env.example` / `.env.prod.example`: 添加 `CRAWL_CONCURRENCY` 注释

**验证**: 配置可通过环境变量覆盖

### Part 2: HTTP 客户端线程安全
- [ ] 确认 `SourceRegistry.get()` 是否返回单例
- [ ] 如果单例：在 `PipelineRunner.run()` 入口为 source 创建新的 `CrawlerHttpClient` 实例
- [ ] 或：改 `SourceRegistry.get()` 为工厂方法，每次返回新实例

**验证**: 多线程并发调用不出 race condition

### Part 3: fetch_cities 缓存
- [ ] `PipelineRunner.run()` 新增参数 `city_map: dict[str, int] | None = None`
- [ ] `_load_dimensions` 当 `city_map` 已传入时跳过 `fetch_cities` 和 `upsert_cities`，只做 `fetch_districts`
- [ ] `run_collect` 入口：单次 `fetch_cities` + `upsert_cities`，传 city_map 给每个城市的 pipeline

**验证**: 日志中 `fetch_cities` 只出现一次

### Part 4: 并发编排
- [ ] `collect_tasks.py`: 重构 `run_collect` 为 semaphore + gather 并发模式
- [ ] 进度上报加 `asyncio.Lock`
- [ ] 每个城市任务独立处理错误，不影响其他城市
- [ ] 定时路径（`inter_city_delay` / `max_consecutive_failures` 有值时）保持串行

**验证**: 
```bash
# 在容器内跑 6 城市采集，观察：
# 1. 耗时 < 3 分钟（之前 ~12 分钟）
# 2. 进度数字单调递增
# 3. 所有城市数据正常入库
```

### Part 5: 测试更新
- [ ] 更新 `run_collect` 相关测试用例
- [ ] 添加并发场景的测试（mock HTTP，验证 semaphore 限流）
- [ ] 确保现有 pipeline 测试不受影响

**验证**: `pytest` 全通过

## 回滚方案

设 `CRAWL_CONCURRENCY=1` 即回退为串行模式（semaphore(1) = 互斥锁 = 串行）。
