# 管理端数据与地图采集

## Goal

管理员可在前端「数据管理」页完成：查看全国城市及其数据/地图覆盖状态 → 触发选中城市的数据采集 → 触发地图（GeoJSON）爬取 → 实时查看任务进度与历史。为此需要建立轻量后台任务机制，并把 GeoJSON 从前端静态目录迁移为后端存储 + API 提供。

## Requirements

### 后台任务机制（本任务交付，模型训练任务复用）

- 进程内异步执行（asyncio），任务状态持久化到数据库，前端轮询查询；不引入 Celery/APScheduler。
- 任务至少包含：类型、目标（城市）、状态（pending/running/success/failed）、起止时间、错误信息、进度计数（如 已完成城市数/总数）。
- 互斥：同一时间同类任务只允许一个在跑（避免管理员重复点击引发并发采集）。
- 服务重启后，遗留 running 状态的任务标记为 failed（启动时清理），不承诺断点续传（重新触发即可，采集本身幂等 upsert）。

### 采集 API（require_admin）

- `POST /admin/collect/cities/refresh`：从 creprice 刷新全国城市列表入 `city` 表（现有 `fetch_cities` 能力 API 化）。
- `GET /admin/collect/cities`：城市列表 + 数据覆盖状态（有无区县/最新快照月份）+ 有无地图，支持关键词/省份筛选与分页。
- `POST /admin/collect`：body 传城市 code 列表（或 `all=true`），创建采集任务后台执行现有 pipeline（采集→清洗→入库→缓存失效），逐城市推进并更新进度。
- `GET /admin/jobs`（支持 kind 过滤）、`GET /admin/jobs/{id}`：任务列表/详情（含进度与每城市结果摘要）。命名取通用前缀，供后续训练任务（admin-model-mgmt）复用同一组查询端点。

### 地图爬取与 GeoJSON 服务化

- `fetch_geo.py` 核心逻辑重构为可复用模块，GeoJSON 落盘到后端侧目录（不再写 `frontend/public/geo/`）。
- `POST /admin/geo/fetch`：body 传城市 code 列表（或缺图城市全量），后台任务逐城市下载边界数据。
- `GET /api/v1/geo/{city_code}`：向所有登录用户提供 GeoJSON（前端地图组件改为从该接口加载）。
- 迁移现有 3 份 geo 文件（fz/qz/xm）到新存储位置；`frontend/public/geo/` 移除。

### 前端「数据管理」页（新增 DataManageView）

- 路由 `/admin/data`，`requiresAdmin`，AppHeader 管理员菜单加入口。
- 城市表格：名称/省份/区县数/最新数据月份/地图状态，多选 + 「采集所选」「爬取所选地图」「刷新城市列表」按钮，及「采集全部缺数据城市」「补齐全部缺图」快捷操作。
- 任务区：进行中任务的进度展示（轮询，如每 3s），历史任务列表（状态、耗时、错误）。
- 有任务运行时禁用触发按钮（与后端互斥一致）。

## Constraints

- 数据源仅 creprice；采集保持现有限速/重试策略，本任务不调整反爬参数。
- 地图数据源仍为阿里 DataV GeoAtlas；city 表按需补充 adcode 字段以避免每次在线重建索引。
- 生产 uvicorn workers=2：任务状态一律以 DB 为准（任一 worker 可查）；触发请求由哪个 worker 接到就在哪个 worker 执行。

## Acceptance Criteria

- [x] 数据管理页点「刷新城市列表」后，城市表格出现全国数百城市（368 城，带省份），覆盖状态列正确（qz E2E 断言有数据有图，未采集城市显示无）。
- [x] 选择 1 个新城市触发采集：莆田采集任务进度实时推进，完成后普通用户端 /cities 可见、区县概览数据完整（76 快照/106 分布）。
- [x] 对新城市触发地图爬取：三明经 UI 实测地图状态即时翻转「有」；prod 形态实测龙岩爬图 success 后 geo API 立即 200（nginx 镜像无需重建）。
- [x] 任务运行中重复触发同类任务 409（pytest），前端任务进行中全部触发按钮禁用（浏览器实测）。
- [x] 重启清理机制经单测验证（遗留 running→failed、幂等、终态不受影响）；采集 upsert 幂等由既有管线保证。
- [x] 旧 `frontend/public/geo/` 已删除且无引用；E2E 地图用例（大屏 + 新增 geo API 加载）通过。
- [x] 新增端点 34 个 pytest 用例（job_runner 8 + 采集 14 + geo 8 + 解析扩展等），外部 HTTP/pipeline 全部打桩。
