# Implement — 多源框架泛化与数据源切换（child A）

按小步提交（符合 commit-per-part 约定），每步独立可回退。所有验证在容器内跑（勿在宿主机 uvicorn/vite）。

## Step 1 — 能力抽象（无行为变化）
- [ ] `base.py`：加 `DataType` 常量类；`BaseSource` 加类级 `capabilities`（默认 `{CITIES, PRICE_TIMELINE}`）、`price_unit="cny_per_sqm"`、`base_url=""`、`supports()` classmethod；`fetch_districts`/`fetch_price_distribution` 加 `NotImplementedError` stub；`SourceRegistry.get_class()`。
- [ ] `creprice.py`：加 `capabilities`（满 4 能力）、`base_url`（保留 `BASE_URL` 别名）。
- 验证：`docker compose exec backend python -c "from app.collector.base import SourceRegistry,DataType; c=SourceRegistry.get_class('creprice'); print(c.capabilities, c.supports(DataType.DISTRICTS))"`
- commit: `feat(collector): 源能力声明 capabilities/DataType/get_class`

## Step 2 — 编排按能力跳步 + 去 BASE_URL 硬编码
- [ ] `runner.py`：`run()` 用 `supports_dist`/`supports_distribution` 包裹区县时序、城市分布、区县分布；`_load_dimensions` 加 `with_districts` 参数并跳过 `fetch_districts`；两处 `source.BASE_URL` → `getattr(source, "base_url", "") or source.source_name`。
- 验证：单测 stub 一个仅 `{CITIES, PRICE_TIMELINE}` 的假源，`run()` 不调用 districts/distribution 不报错；creprice 路径回归。
- commit: `refactor(pipeline): runner 按源能力自适应跳步`

## Step 3 — 去硬编码源名 + KV 默认源 + 请求覆盖
- [ ] `app_settings.py`：加 `COLLECT_SOURCE_KEY`、`DEFAULT_SOURCE`、async `get_collect_source/set_collect_source`。
- [ ] `schemas/admin_job.py`：`CollectRequest` 加 `source: str | None = None`。
- [ ] `admin_collect.py`：删 `SOURCE_NAME`；加 `_resolve_source`（未注册 422）；`refresh_cities`/`submit_collect`/`_run_collect` 运行时解析源（`payload.source > get_collect_source > DEFAULT`）；job payload 落 `source`。
- 验证：`POST /admin/collect {city_codes:[...]}` 不带 source 仍走 creprice；带非法 source → 422。
- commit: `feat(api): 采集源运行时解析（请求 > KV > 默认），去硬编码 SOURCE_NAME`

## Step 4 — 迁移 004 + source 注记列
- [ ] `models/price_snapshot.py`：加 `source: Mapped[str|None]`（String(20)）。
- [ ] `alembic/versions/004_price_snapshot_source.py`：add_column 可空 + 幂等回填 `creprice`；downgrade drop 列。
- [ ] `loaders.py`：`upsert_price_snapshots` 加 `source` 入参，写入 + 进 `on_conflict.set_`。
- [ ] `runner.py`：`_load_city_timeline`/`_load_district_timeline` 透传 `source.source_name`。
- 验证：backend 重启自动 upgrade；`\d price_snapshot` 有 source 列；采集一城后该行 `source='creprice'`；`alembic downgrade 003` 可逆再 upgrade。
- commit: `feat(db): price_snapshot.source 溯源列 + 迁移 004`

## Step 5 — 数据源切换端点
- [ ] `schemas/admin_job.py`：`CollectSourceOut`/`CollectSourcesResponse`/`CollectSourceUpdate`。
- [ ] `admin_collect.py`：`GET /sources`（列源+能力+当前）、`PUT /source`（写 KV，非法 422）。
- 验证：`GET /admin/collect/sources` 含 creprice 满能力+current；`PUT /source {source:"creprice"}` 生效；非法 422。
- commit: `feat(api): GET/PUT 数据源切换端点`

## Step 6 — 前端数据源卡片
- [ ] `types/index.ts`：`CollectSource`/`CollectSourcesResponse`。
- [ ] `api/admin.ts`：`fetchCollectSources`/`saveCollectSource`。
- [ ] `DataManageView.vue`：`source-card`（复用 proxy-card 风格），`el-select` 切源 + 能力 `el-tag`；onMounted 载入。
- 验证：Playwright 登录 admin → 数据管理页，看到数据源卡片，切换后 `ElMessage.success` 且刷新保持。
- commit: `feat(frontend): 数据管理页「数据源」切换卡片`

## 收尾
- [ ] 全量后端测试 `docker compose exec backend pytest`；creprice 抽查采集一城端到端验证。
- [ ] 更新 spec（如 backend/frontend index 有采集相关条目）。

## 验证命令速查
- 后端测试：`docker compose exec backend pytest -q`
- 迁移状态：`docker compose exec backend alembic current`
- 源能力：见 Step 1 验证行
