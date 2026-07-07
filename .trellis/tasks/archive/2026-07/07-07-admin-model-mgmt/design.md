# 管理端模型管理 — 技术设计

## 后端改造

### 训练任务化（app/api/v1/predictions.py）

- `POST /admin/predict/train`：改为 `job_runner.submit(kind='train', payload=TrainRequest, coro_factory=...)`，返回 `{job_id}`（真 202）。任务体调用现有 `train_model(...)`——它是同步 CPU 密集函数，须 `asyncio.to_thread` 包装，避免阻塞事件循环（uvicorn worker 内其他请求仍可响应）。
- 训练结果（新版本号、指标 dict）写入 `admin_job.result`；异常置 failed + error。
- 互斥沿用 job_runner 的 kind 级互斥（train 与 collect 互不影响）。
- 任务查询走统一 `GET /admin/collect/jobs?kind=...`？——路径语义不符。定为：把任务查询端点归位为 `GET /admin/jobs`（list，支持 kind 过滤）+ `GET /admin/jobs/{id}`，admin-data-collect 实施时即按此命名（在该任务 implement 中同步修正），本任务直接复用，无新增查询端点。
- `GET /admin/predict/models`：确认 `ModelVersionOut` 含 `trained_at`、`metrics`（读 meta.json），缺则补字段。

### 复用契约（依赖 admin-data-collect）

- `job_runner.submit` / `admin_job` 表 / 启动清理 / 409 语义，均不在本任务重复实现。

## 前端

- `views/admin/ModelManageView.vue`：
  - 上：版本 el-table（算法/版本/trained_at/MAPE/活跃 tag/「设为活跃」按钮，活跃行禁用）。
  - 下：训练卡片（算法 select、城市 select 多选默认全部、提交按钮）+ 进行中任务 el-progress（轮询 3s，复用 DataManageView 的轮询模式，可抽 composable `useJobPolling(kind)`）。
- `api/predict.ts`（或新建 `api/models.ts`）：`fetchModelVersions` / `setActiveModel` / `submitTrain` / 复用 `fetchJobs(kind)`。
- 路由 + AppHeader 菜单项，与用户管理/数据管理并列。

## 风险与注意

- `asyncio.to_thread` 中的 train_model 使用同步 DB 读数（现有实现基于 pandas 读库），确认其内部使用 `database_url_sync` 独立连接，不与异步 session 混用。
- 训练数据量增大后（全量城市），训练耗时上升——进度无法细分（train_model 无回调），progress 仅 0/1 → 1/1，前端展示「训练中」状态即可，不做假进度条。
- 回滚：revert 提交即可（无新迁移，admin_job 表由前置任务拥有）。
