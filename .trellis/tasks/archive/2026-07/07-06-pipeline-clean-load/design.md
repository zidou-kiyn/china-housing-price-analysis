# 技术设计 - 清洗管线与入库

## 模块边界

```
backend/app/pipeline/
├── __init__.py
├── runner.py          # PipelineRunner 编排器
├── cleaners.py        # 清洗函数（纯函数，无副作用）
└── loaders.py         # DB upsert 操作（async）
```

## 数据流

```
PipelineRunner.run(source, city_code)
  │
  ├─ 1. create crawl_job (status=running)
  │
  ├─ 2. fetch_cities + fetch_districts → upsert city/district → code→id map
  │
  ├─ 3. fetch_price_timeline(city, "allsq1") → clean → upsert price_snapshot (region_type="city")
  │     + 记录 crawl_log
  │
  ├─ 4. for each district:
  │     fetch_price_timeline(city, dist_code) → clean → upsert price_snapshot (region_type="district")
  │     + 记录 crawl_log
  │
  ├─ 5. fetch_price_distribution(city, "allsq1") → clean → upsert price_distribution
  │     + 记录 crawl_log
  │
  ├─ 6. invalidate redis cache
  │
  └─ 7. update crawl_job (status=completed/failed)
```

## 关键设计

### 同步/异步桥接

采集器用 `requests`（同步），DB 用 `AsyncSession`。方案：

```python
async def run(self, source: str, city_code: str):
    raw = await asyncio.to_thread(self.source.fetch_price_timeline, city_code)
    cleaned = clean_price_timeline(raw.records)
    await upsert_price_snapshots(session, cleaned, region_type, region_id)
```

### Upsert 策略

使用 PostgreSQL `INSERT ... ON CONFLICT ... DO UPDATE`（via `sqlalchemy.dialects.postgresql.insert`）：

```python
from sqlalchemy.dialects.postgresql import insert

stmt = insert(PriceSnapshot).values(rows)
stmt = stmt.on_conflict_do_update(
    constraint="uq_price_snapshot_region_month",
    set_={
        "supply_price": stmt.excluded.supply_price,
        "attention_price": stmt.excluded.attention_price,
        "value_price": stmt.excluded.value_price,
        "sample_count": stmt.excluded.sample_count,
    }
)
```

### 清洗规则

| 数据类型 | 规则 | 处理 |
|---------|------|------|
| price_timeline | supply/attention/value 全为 None | 丢弃该行 |
| price_timeline | 价格 ≤ 0 或 ≥ 200000 | 置为 None |
| price_distribution | percentage == 0 | 丢弃该行 |
| price_distribution | low ≥ high | 丢弃该行 |

### CrawlLog 记录时机

每次 `fetch_*` 调用包装为 `_fetch_and_log()`，记录：
- url: RawRecord.raw_url
- status_code: 200（成功时）或 None（异常时）
- success: bool
- raw_path: storage.save_raw() 返回值
- record_count: len(raw.records)
- elapsed_ms: 调用耗时（ms）

### Redis 缓存失效

入库完成后执行：
```python
await redis.delete(*keys)  # 匹配 price:{city_code}:* 和 trend:{city_code}:*
```

由于 M1 阶段 API 尚未实现，缓存 key 模式未定，此步骤先做占位（scan+delete），后续 API 任务中对齐。

## 兼容性

- 管线不依赖具体 Source 实现，通过 SourceRegistry 获取适配器
- 新数据源只需实现 BaseSource 接口，PipelineRunner 无需修改
