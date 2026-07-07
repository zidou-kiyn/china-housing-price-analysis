# M1-4 清洗管线与入库

## Goal

实现从 creprice 原始采集数据到 PostgreSQL 入库的完整管线：城市/区县维度表 upsert → 均价时序清洗入库 → 价格分布清洗入库 → crawl_job/crawl_log 记录 → Redis 缓存失效。以泉州（qz）为首个打通城市。

## Requirements

- **管线编排器** `PipelineRunner`：
  - 接受 source name + city_code，执行端到端采集→清洗→入库流程
  - 创建 `crawl_job` 记录跟踪整体进度（pending → running → completed/failed）
  - 每次 HTTP 请求记录 `crawl_log`（URL、状态、耗时、raw_path、record_count）

- **维度表 upsert**：
  - 调用 `CrepriceSource.fetch_cities()` / `fetch_districts()` 获取城市/区县列表
  - upsert 到 `city` / `district` 表（code 为唯一键）
  - 返回 code → id 映射字典

- **均价时序入库**：
  - 调用 `fetch_price_timeline(city_code, district_code)` 获取 RawRecord
  - 清洗：过滤全 None 记录、价格范围校验（0 < price < 200000）
  - upsert 到 `price_snapshot`（唯一键：region_type + region_id + year_month）
  - 城市整体用 district_code="allsq1"，region_type="city"
  - 各区县逐个请求，region_type="district"

- **价格分布入库**：
  - 调用 `fetch_price_distribution(city_code, district_code)` 获取 RawRecord
  - 清洗：过滤 percentage=0 或范围异常的记录
  - year_month 从 fetched_at 取当月（原始数据不含时间）
  - upsert 到 `price_distribution`（唯一键：region_type + region_id + year_month + price_range_low）

- **Redis 缓存失效**：
  - 入库完成后删除匹配 `price:*` 和 `trend:*` 的相关 key

## Constraints

- 采集器（CrawlerHttpClient）是同步的，DB 是异步的；管线用 `asyncio.to_thread` 桥接同步 HTTP 调用
- 每次 HTTP 请求间隔 1~3s（采集器内置），管线不额外限速
- 单城市管线失败不影响其他城市

## Acceptance Criteria

- [ ] `PipelineRunner.run("creprice", "qz")` 完整执行无报错
- [ ] city 表有泉州记录，district 表有对应区县
- [ ] price_snapshot 表有泉州城市级 ≥12 个月的记录
- [ ] price_snapshot 表有各区县的记录
- [ ] price_distribution 表有泉州当月分布数据
- [ ] crawl_job 记录状态为 completed，crawl_log 记录了所有请求的 URL、耗时
- [ ] 重复执行管线不产生重复数据（upsert 幂等）
- [ ] 单元测试覆盖清洗逻辑和 upsert 逻辑

## Dependencies

- M1-1 infra-scaffold（项目结构、DB 连接）✅
- M1-2 db-schema（ORM 模型、Alembic 迁移）✅
- M1-3 collector-creprice（采集适配器）✅
