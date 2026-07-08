# 采集流程并发优化 — 技术设计

## 架构概述

当前流程：`run_collect` → for 循环逐城市 → `PipelineRunner.run()` → 同步 HTTP（asyncio.to_thread）

改造后：`run_collect` → asyncio.Semaphore(N) + gather 并发 → 每城市独立 PipelineRunner.run()

## 变更边界

### 1. `config.py` — 新增并发配置

```python
crawl_concurrency: int = 5              # 城市间最大并发数
crawl_request_delay_min: float = 0.3    # 默认值从 1.0 降至 0.3
crawl_request_delay_max: float = 0.8    # 默认值从 3.0 降至 0.8
```

### 2. `collect_tasks.py` — 并发编排

核心改造点。当前 `run_collect` 是 `for code in city_codes` 串行循环。

改为：
- `asyncio.Semaphore(settings.crawl_concurrency)` 控制并发
- `asyncio.gather(*tasks)` 并发执行
- 每个城市任务用 semaphore 限流
- 进度计数器用 `asyncio.Lock` 保护（`report_progress` 需要严格递增的计数）

```python
async def _run_one_city(sem, runner, source_name, code, progress, lock, ...):
    async with sem:
        try:
            stats = await runner.run(source_name, code)
            result = {"city": code, "ok": True, ...}
        except Exception as exc:
            result = {"city": code, "ok": False, "error": str(exc)[:500]}
        async with lock:
            progress["done"] += 1
            progress["results"].append(result)
            await job_runner.report_progress(job_id, progress["done"], result=progress["results"])
        return result
```

熔断逻辑（`max_consecutive_failures`）：并发场景下"连续失败"的语义不再精确（多个城市同时失败不等于连续）。定时路径可改为"失败率超阈值"或简单保留顺序执行模式。手动路径不受影响（不使用熔断）。

### 3. `runner.py` — fetch_cities 缓存

`_load_dimensions` 当前每城市调 `source.fetch_cities()`。改为：
- `run_collect` 入口调一次 `fetch_cities` + `upsert_cities`，得到 `city_map`
- `PipelineRunner.run()` 新增可选参数 `city_map: dict | None`
- 传入 `city_map` 时跳过 `fetch_cities`，只调 `fetch_districts`

### 4. HTTP 客户端线程安全

`CrawlerHttpClient` 基于 `requests.Session`，Session 不是线程安全的。并发场景下每个城市的 pipeline 运行在 `asyncio.to_thread` 中，意味着多线程并发访问。

解决方案：`CrepriceSource` 在每次被 `PipelineRunner.run()` 使用时创建新的 HTTP client 实例。当前 `SourceRegistry.get()` 返回的是源实例，其 `client` 在 `__init__` 中创建。需确认是否每次 `get()` 返回新实例，如果是单例则需改为工厂模式或在 `run()` 入口重建 client。

## 数据流

```
POST /admin/collect {city_codes: [...]}
  └─ run_collect(job_id, city_codes, source_name)
       ├─ fetch_cities() 一次 → city_map
       ├─ Semaphore(5) + gather:
       │    ├─ city_1: PipelineRunner.run(city_map=city_map)
       │    ├─ city_2: PipelineRunner.run(city_map=city_map)
       │    ├─ city_3: ...
       │    └─ (等待空位) city_6, city_7, ...
       └─ 汇总 results
```

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| creprice 对高并发限流 | 默认 5 并发 + 0.3-0.8s sleep，可通过环境变量调低 |
| 数据库连接池耗尽 | 每个 PipelineRunner 使用独立 session（已有 session_factory 机制） |
| 进度数字乱序 | asyncio.Lock 保护 progress 更新 |
| 定时路径熔断语义变化 | 定时路径暂保持串行模式，只有手动路径并发 |

## 不变的部分

- API 接口不变
- 数据入库逻辑不变（upsert ON CONFLICT）
- 原始文件存储路径不变
- 用户代理配置不变
- 重试/退避逻辑不变
