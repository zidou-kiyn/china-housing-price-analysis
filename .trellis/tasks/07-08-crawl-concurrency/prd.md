# 采集流程并发优化

## Goal

将数据采集从串行执行改为并发执行，消除冗余请求，将 368 城全量采集耗时从 ~11 小时降至 <1 小时。

## Background

当前瓶颈分析（实测确认）：
- `CrawlerHttpClient.get()` 每次请求前 sleep 1-3s（均值 2s）
- 所有城市串行执行，零并发
- `fetch_cities()` 被每个城市重复调用（368 次相同请求）
- 单个城市 ~24 个请求 × ~2s sleep ≈ 2 分钟
- 未被 creprice.cn 封锁或限流（实测确认）

## Requirements

### R1: 城市间并发采集
- 在 `run_collect` 层面引入 `asyncio.Semaphore` 控制并发度
- 默认并发数 5（可通过环境变量调整）
- 每个并发城市使用独立的 HTTP client 实例（线程安全）

### R2: 缩短请求间 sleep
- `CRAWL_REQUEST_DELAY_MIN` 默认值从 1.0 降至 0.3
- `CRAWL_REQUEST_DELAY_MAX` 默认值从 3.0 降至 0.8
- 用户仍可通过 .env 覆盖

### R3: 消除冗余 fetch_cities 调用
- `fetch_cities()` 在管线入口调用一次，结果传入各城市 pipeline
- `_load_dimensions` 不再自行调用 `fetch_cities()`

### R4: 并发进度上报
- 多个城市并发完成时，进度计数和 results 列表需线程安全更新
- `job_runner.report_progress` 调用需串行化或加锁

### R5: 向后兼容
- 不改变 API 接口（`POST /admin/collect` 请求/响应格式不变）
- 不改变用户可配置的代理功能
- 定时采集路径的 `inter_city_delay` / `max_consecutive_failures` 参数继续生效

## Acceptance Criteria

- [ ] 6 城采集耗时从 ~12 分钟降至 <3 分钟（实测）
- [ ] `fetch_cities()` 在一次采集任务中只被调用 1 次（日志可验证）
- [ ] 并发采集过程中进度数字单调递增，不跳跃不重复
- [ ] 单城市失败不影响其他城市继续采集
- [ ] 现有测试全部通过
- [ ] .env 中 `CRAWL_REQUEST_DELAY_MIN/MAX` 仍可覆盖默认值
