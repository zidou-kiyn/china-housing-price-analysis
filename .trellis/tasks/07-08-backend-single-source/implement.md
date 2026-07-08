# 后端多源代码清理与单源硬编码 — 执行计划

## 前置条件

- 07-08-db-restructure 已完成（ORM 模型已删除）

## 步骤

### 1. 删除采集器文件

```bash
rm backend/app/collector/sources/gov_stats.py
rm backend/app/collector/sources/kaggle_lianjia.py
rm backend/app/collector/sources/listing_annual.py
```

- 检查 `collector/sources/__init__.py` 是否有导入，如有则清理

### 2. 删除服务文件

```bash
rm backend/app/services/nationwide_import.py
rm backend/app/services/index_import.py
rm backend/app/services/data_quality.py
rm backend/app/services/collect_scheduler.py
rm backend/app/services/geo.py
```

### 3. 删除 API 路由文件

```bash
rm backend/app/api/v1/admin_data_quality.py
rm backend/app/api/v1/geo.py
```

### 4. 精简 source_policy.py

编辑 `backend/app/core/source_policy.py`：只保留 creprice 相关定义。

### 5. 清理 main.py

- 移除 `from app.services.collect_scheduler import collect_scheduler`
- 移除 `_scheduler_enabled()` 函数
- 移除 lifespan 中的 `collect_scheduler.start()` 和 `collect_scheduler.stop()`

### 6. 清理 API 路由注册

- 从路由注册处移除 `admin_data_quality` 和 `geo` 路由
- 从 `admin_collect.py` 移除导入端点（import_annual、import_index）
- 从 `admin_settings.py` 移除定时采集配置端点

### 7. 清理 admin_collect.py

- 移除 `has_geo` 字段相关代码（geo 目录扫描逻辑）
- 移除导入相关端点
- 移除分页参数（全量返回 — 配合 ui-overhaul）

### 8. 删除 data/geo/ 目录

```bash
rm -rf data/geo/
```

更新 `.gitignore` 和 `.dockerignore` 中的 `data/geo` 条目（如有）。

### 9. 引用扫描验证

```bash
grep -rn "gov_stats\|kaggle_lianjia\|listing_annual" backend/app/
grep -rn "nationwide_import\|index_import\|data_quality\|collect_scheduler" backend/app/
grep -rn "from app.services.geo\|from app.api.v1.geo" backend/app/
grep -rn "PriceIndexSnapshot\|price_index_snapshot" backend/app/
```

所有 grep 应返回 0 结果（除了 alembic migration 文件中的历史引用）。

### 10. 启动验证

```bash
docker compose up -d --build
docker compose logs backend --tail 50
# 确认无 ImportError，app 正常启动
```

### 11. 采集功能验证

```bash
# 通过 API 手动触发一个城市的采集，验证 creprice 采集管线仍工作
curl -X POST http://localhost:8000/api/v1/admin/collect/start \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"city_codes": ["bj"]}'
```

## 回滚方案

- `git checkout -- backend/app/` 恢复全部删除的文件
- 无数据库变更，无需 alembic downgrade
