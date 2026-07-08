# 数据库结构精简与种子数据初始化 — 技术设计

## 概览

通过一个 Alembic migration 完成表结构变更（DROP 4 表 + TRUNCATE 7 表 + 清空 app_setting），同时删除对应的 ORM 模型文件。在 FastAPI lifespan 中增加种子数据加载逻辑，实现 city 表的自动填充。

## 数据流

```
docker compose up
  → alembic upgrade head（migration 007）
    → DROP area, community, listing, price_index_snapshot（IF EXISTS）
    → TRUNCATE district, price_snapshot, price_distribution, prediction,
              admin_job, crawl_job, crawl_log（CASCADE）
    → DELETE FROM app_setting
  → uvicorn app.main:app
    → lifespan startup
      → cleanup_stale_jobs()
      → seed_cities_if_empty()  ← 新增
        → SELECT COUNT(*) FROM city
        → 如果为 0，读取 seed/cities.json，批量 INSERT
```

## 关键设计决策

### Migration 007：结构变更

- 使用 `op.execute("DROP TABLE IF EXISTS ...")` 而非 `op.drop_table()`，避免全新库无旧表时报错
- TRUNCATE 使用 CASCADE 处理外键依赖（district → city 的 FK 不 TRUNCATE city，只 TRUNCATE district）
- app_setting 用 DELETE 而非 TRUNCATE（无外键，且保留表结构）
- downgrade 不恢复数据（不可逆操作），仅重建被 DROP 的表结构

### 种子数据

- 格式：JSON 数组，每项 `{name, code, province, adcode}`
- 存放：`backend/seed/cities.json`
- 加载时机：lifespan startup，在 `cleanup_stale_jobs()` 之后
- 加载逻辑：独立函数 `seed_cities_if_empty()`，放在 `app/services/seed.py`
- 幂等性：仅当 `SELECT COUNT(*) FROM city` 为 0 时执行

### ORM 模型删除

删除 4 个文件：`area.py`、`community.py`、`listing.py`、`price_index_snapshot.py`

从 `models/__init__.py` 移除 4 个导出：`Area`、`Community`、`Listing`、`PriceIndexSnapshot`

注意：`alembic/env.py` 有 `from app.models import *`，删除模型后 alembic autogenerate 不会再追踪这些表，这正是预期行为。

### District 外键

`district` 表有 FK 指向 `city`。TRUNCATE district 但不 TRUNCATE city。种子数据只填充 city，district 在首次采集时由 pipeline 自动填充。

## 兼容性

| 场景 | 行为 |
|---|---|
| 全新库（首次 alembic upgrade head） | migration 001-006 创建所有表，007 立即 DROP 4 张 + TRUNCATE 7 张（空操作）。lifespan 种子填充 city。 |
| 旧库升级 | 007 DROP 4 张旧表 + TRUNCATE 清空数据。lifespan 种子填充 city（如果旧 city 数据存在则不填充——需用户手动清空或我们在 migration 中也 TRUNCATE city）。 |

### 旧库的 city 表处理

旧库 city 表已有数据，种子数据不会覆盖（COUNT > 0 跳过）。这是正确行为——旧库的城市数据可能已经通过刷新按钮更新过，不应被种子数据回退。
