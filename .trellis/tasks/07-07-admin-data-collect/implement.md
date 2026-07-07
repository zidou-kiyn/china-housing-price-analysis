# 管理端数据与地图采集 — 执行计划

前置：compose-unify 已完成（dev 全容器化）；所有命令在 `docker compose exec backend` / 宿主机 frontend 目录下执行。

## Part 1：任务机制与数据模型（可独立提交）

- [x] 新增 `app/models/admin_job.py` + `city.adcode` 列；Alembic 迁移（一个 revision 两张表变更）
- [x] `app/services/job_runner.py`：submit / 互斥（含部分唯一索引）/ 状态流转 / lifespan 启动清理
- [x] pytest：job_runner 单测（成功流转、异常置 failed、互斥 409、重启清理）
- 验证：`docker compose exec backend uv run pytest tests/ -k job` 通过；`alembic upgrade head` 干净执行
- 回滚点：迁移可 downgrade

## Part 2：采集 API + 城市覆盖查询（可独立提交）

- [x] `POST /admin/collect/cities/refresh`（同步，调 CrepriceSource.fetch_cities）
- [x] `GET /admin/collect/cities`（覆盖状态：区县数/最新月份/有无地图，keyword/province/分页）
- [x] `POST /admin/collect`（admin_job kind=collect，任务体循环 PipelineRunner.run，逐城市进度与 result 摘要）
- [x] `GET /admin/jobs`（kind 过滤）、`GET /admin/jobs/{id}`；schema 入 `app/schemas/admin_job.py`
- [x] pytest：路由用例（外部 HTTP 打桩 / PipelineRunner monkeypatch；权限 403；互斥 409）
- 验证：pytest 通过；手动 `curl` 触发一个小城市采集，DB 中 admin_job 进度推进、快照入库

## Part 3：GeoJSON 服务化（可独立提交）

- [x] `config.geo_dir` + `app/services/geo.py`（下载/落盘/读取/列表/adcode 回填）
- [x] `POST /admin/geo/fetch`（admin_job kind=geo_fetch）+ `GET /api/v1/geo/{city_code}`
- [x] `scripts/fetch_geo.py` 改为薄 CLI 调 service；迁移现有 3 份 geo 文件到 `data/geo/`
- [x] compose 基准文件确认 backend 挂载可写 `./data`（与 compose-unify 产物核对）
- [x] pytest：geo 端点 404/成功、adcode 回填打桩用例
- 验证：`curl /api/v1/geo/qz` 返回 GeoJSON；触发 fetch 任务补一个新城市地图成功

## Part 4：前端数据管理页（可独立提交）

- [x] `api/admin.ts` + `types/index.ts` 扩展（cities/collect/jobs/geo + AdminJob/CityCoverage 类型）
- [x] `views/admin/DataManageView.vue`（城市表多选/筛选/分页 + 触发按钮 + 任务进度轮询 + 历史表）
- [x] 路由 `/admin/data`（requiresAdmin）+ AppHeader 菜单项
- [x] 前端地图加载改走 geo API（替换 `/geo/xx.json` 引用，删 `frontend/public/geo/`），带内存缓存
- [x] E2E：数据管理页触发采集（打桩或小城市真跑）+ 地图经 API 加载用例；注意 Element Plus 已知坑（memory）
- 验证：`npm run lint && npm run type-check && npm run test:e2e`；浏览器手动全流程走查

## 完成门槛（最后一轮全量检查）

- [x] prd.md 验收标准逐条勾验
- [x] 后端 `uv run pytest`（全量）+ 覆盖率不低于现有基线（72%）
- [x] 前端 lint / type-check / e2e 全绿
- [x] dev 与 prod 两种 compose 形态下手动验证「采集 + 爬图 + 前端展示」闭环
