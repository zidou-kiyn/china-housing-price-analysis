# 数据库结构精简与种子数据初始化 — 执行计划

## 前置条件

- 当前数据库有数据（用于导出种子数据）
- docker compose 环境可用

## 步骤

### 1. 导出种子数据

```bash
# 从运行中的数据库导出 city 表为 JSON
docker compose exec postgres psql -U postgres -d housing_price -t -A -c \
  "SELECT json_agg(json_build_object('name',name,'code',code,'province',province,'adcode',adcode) ORDER BY id) FROM city" \
  > backend/seed/cities.json
```

- 验证：文件包含 330+ 条记录，每条有 name/code/province/adcode
- 格式化 JSON 以便阅读

### 2. 删除 ORM 模型文件

删除以下文件：
- `backend/app/models/area.py`
- `backend/app/models/community.py`
- `backend/app/models/listing.py`
- `backend/app/models/price_index_snapshot.py`

编辑 `backend/app/models/__init__.py`：
- 移除 `Area`、`Community`、`Listing`、`PriceIndexSnapshot` 的 import 和 `__all__` 条目

### 3. 创建 Alembic migration 007

文件：`backend/alembic/versions/007_simplify_schema.py`

内容：
- `upgrade()`：
  - `op.execute("DROP TABLE IF EXISTS area CASCADE")`
  - `op.execute("DROP TABLE IF EXISTS community CASCADE")`
  - `op.execute("DROP TABLE IF EXISTS listing CASCADE")`
  - `op.execute("DROP TABLE IF EXISTS price_index_snapshot CASCADE")`
  - `op.execute("TRUNCATE TABLE district, price_snapshot, price_distribution, prediction, admin_job, crawl_job, crawl_log CASCADE")`
  - `op.execute("DELETE FROM app_setting")`
- `downgrade()`：
  - 注释说明不可逆，仅重建被 DROP 的 4 张表结构（从 001_init_schema.py 和 006 中复制 CREATE TABLE）

- revision 依赖：`down_revision = "006_..."` （需查看 006 的 revision ID）

**验证命令**：
```bash
docker compose exec backend uv run alembic upgrade head
docker compose exec postgres psql -U postgres -d housing_price -c "\dt"
```

### 4. 创建种子数据加载服务

文件：`backend/app/services/seed.py`

```python
async def seed_cities_if_empty() -> None:
    """city 表为空时从 seed/cities.json 导入种子数据。"""
    # 1. SELECT COUNT(*) FROM city
    # 2. 如果 > 0，return
    # 3. 读取 seed/cities.json
    # 4. 批量 INSERT INTO city (name, code, province, adcode)
    # 5. 日志：logger.info("Seeded %d cities", count)
```

### 5. 集成到 FastAPI lifespan

编辑 `backend/app/main.py`：
- import `seed_cities_if_empty`
- 在 lifespan 函数中，`cleanup_stale_jobs()` 之后调用 `await seed_cities_if_empty()`
- 移除 `collect_scheduler` 相关的 import 和 start/stop 调用（属于 backend-single-source 子任务，但如果先做本任务需保留）

**注意**：本任务不删除 collect_scheduler，那是 backend-single-source 子任务的工作。

### 6. 验证

```bash
# 重建数据库验证全新部署
docker compose down -v
docker compose up -d
# 检查 city 表
docker compose exec postgres psql -U postgres -d housing_price -c "SELECT COUNT(*) FROM city"
# 预期：330+
# 检查被删除的表不存在
docker compose exec postgres psql -U postgres -d housing_price -c "\dt area"
# 预期：Did not find any relation
```

## 回滚方案

- Alembic downgrade（重建 4 张空表，但数据不可恢复）
- 如需完全回退，从 Git 历史恢复模型文件 + `alembic downgrade -1`
