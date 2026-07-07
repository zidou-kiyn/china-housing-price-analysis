# 管理端数据与地图采集 — 技术设计

## 1. 后台任务机制（AdminJob）

### 数据模型

现有 `crawl_job` 语义绑定「单城市单次采集」且被 pipeline 内部写入，不改造它；新增通用表 `admin_job`（Alembic 迁移）：

```
admin_job
  id            PK
  kind          str   -- collect | geo_fetch | train（train 由 admin-model-mgmt 使用）
  status        str   -- pending | running | success | failed
  payload       JSON  -- 入参（城市 code 列表等）
  progress_done int   -- 已完成单元数
  progress_total int
  result        JSON  -- 每单元结果摘要 [{city, ok, records, error}, ...]
  error         str?  -- 整体失败原因
  created_at / started_at / finished_at
```

`crawl_job`/`crawl_log` 保留为 pipeline 内部明细，`admin_job.result` 存管理端展示所需摘要即可。

### 执行器 `backend/app/services/job_runner.py`

- `submit(kind, payload, coro_factory) -> AdminJob`：写 pending 行 → `asyncio.create_task` 包装执行 → 状态流转与异常捕获落库。任务协程内自建 DB session（不能复用请求 session）。
- 互斥：submit 前 `SELECT ... WHERE kind=? AND status IN ('pending','running')`，存在则抛 409。多 worker 下该检查存在竞态，但管理端单人操作场景可接受；用 DB 唯一部分索引（`kind WHERE status IN (...)`）兜底。
- 启动清理：`main.py` lifespan 启动时把遗留 `pending/running` 置为 `failed(error='interrupted by restart')`。注意 workers=2 时两个进程都会执行，UPDATE 幂等无害。
- 进度上报：任务协程持 job id，每完成一个城市 UPDATE progress_done/result。

### 与多 worker 的关系

任务在接收请求的 worker 进程内执行；状态在 DB，任何 worker 都能应答轮询。不做跨进程取消（超出范围）。

## 2. 采集任务流

`POST /admin/collect {city_codes: [...]} → admin_job(kind=collect)`，任务体循环调用现有 `PipelineRunner.run(city_code)`（复用采集→清洗→入库→缓存失效全链路），单城市失败记录到 result 并继续下一城市，整体状态 success（部分失败在 result 中体现）/ failed（全部失败或异常中断）。

`POST /admin/collect/cities/refresh`：直接调 `CrepriceSource.fetch_cities()` upsert `city` 表，同步执行（一次 HTTP 请求，秒级），不走任务机制。

### 城市覆盖状态查询

`GET /admin/collect/cities`：`city` LEFT JOIN district 计数、最新 `price_snapshot` 月份子查询、geo 文件存在性（服务层扫 geo 目录一次做成 set）。分页 + keyword/province 过滤。

## 3. GeoJSON 服务化

- 存储：`data/geo/{city_code}.json`（compose 中 backend 已可写项目 `./data`，需在基准 compose 给 backend 挂 `./data:/data` 或经 env 配置 `GEO_DIR`，与 compose-unify 协调——基准文件 backend 需新增该卷挂载）。
- `app/core/config.py` 增加 `geo_dir` 设置；`app/services/geo.py`：`fetch_city_geo(city)`（从 DataV 下载 `{adcode}_full.json` 落盘）、`geo_path(code)`、`list_available()`。
- `scripts/fetch_geo.py` 改薄：解析参数后调 `app.services.geo`，保留 CLI 兜底。
- adcode：`city` 表加列 `adcode`（迁移）；refresh cities 时不强求，geo 任务首次遇到无 adcode 城市时用现有「全国索引构建」逻辑批量回填（索引构建一次、全表 UPDATE，~35 次请求）。`KNOWN_ADCODES` 硬编码可废弃。
- 读取：`GET /api/v1/geo/{city_code}`（require_user，FileResponse + 404）；前端 `MapChart`/地图 store 从 `/geo/xx.json` 改为 API 封装 `fetchCityGeo(code)`，带前端内存缓存（Map<code, geojson>）。
- 迁移：把 `frontend/public/geo/*.json` 移到 `data/geo/`（git 处理方式：data/ 目前应为 git 忽略，确认后这 3 份作为数据文件随迁移脚本/文档说明，不入库）。

## 4. 前端「数据管理」页

- `views/admin/DataManageView.vue`：上半城市表（el-table 多选 + 筛选 + 分页），下半任务卡片（当前任务 el-progress 轮询 3s）+ 历史任务 el-table。
- `api/admin.ts` 扩展：cities/refresh/collect/jobs/geo 各封装；`types/index.ts` 加 `AdminJob`、`CityCoverage` 类型。
- 轮询实现：`setInterval` + `onUnmounted` 清理；仅当存在 pending/running 任务时轮询。
- 参考 memory「Playwright × Element Plus 坑」处理 el-table 多选与消息框的 E2E 交互。

## 5. 兼容与回滚

- API 全部新增，无破坏性变更；前端地图加载路径变更是唯一行为改动，geo API 上线与前端切换在同一任务内完成。
- 回滚：revert 提交 + `alembic downgrade`（admin_job、city.adcode 两个迁移）。

## 6. 风险

- creprice 反爬：复用现有 http_client 限速；多城市任务串行执行，不并发抓取。
- DataV 接口无鉴权但有频控风险：城市间加固定延时（沿用 fetch_geo 现有间隔策略）。
- 任务协程中 DB session 生命周期：必须每城市短事务，避免长事务锁表。
