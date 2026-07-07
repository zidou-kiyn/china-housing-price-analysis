# 管理端模型管理

## Goal

管理员可在前端「模型管理」页查看模型版本与指标、切换活跃模型、发起异步训练并跟踪进度。修复现有训练 API「假 202 实同步」的问题。

## Requirements

### 后端

- 训练改真后台任务：`POST /admin/predict/train` 改为提交 `admin_job(kind=train)`（复用 admin-data-collect 交付的 job_runner），返回 job id；训练互斥（同时只允许一个训练任务）。
- `GET /admin/predict/train/jobs`（或复用 `GET /admin/collect/jobs?kind=train` 的统一任务查询，实现时二选一并保持一致风格）：查询训练任务状态与结果（含新模型版本号、评估指标）。
- 现有 `GET /admin/predict/models`（版本列表 + is_active）、`PUT /admin/predict/models/active`（切换活跃）保持不变，确认返回信息含训练时间与指标（MAPE 等，读自 meta.json），不足则补充。
- 训练完成后的新版本**不自动激活**，由管理员显式切换。

### 前端（新增 ModelManageView）

- 路由 `/admin/models`，`requiresAdmin`，AppHeader 管理员菜单加入口。
- 模型版本表：算法、版本、训练时间、指标（MAPE 等）、是否活跃；「设为活跃」操作（二次确认 + 成功提示）。
- 训练表单：算法选择（random_forest / xgboost）、训练数据范围（城市，默认全部已采集城市）；提交后展示任务进度（轮询），完成后自动刷新版本表。
- 训练进行中禁用再次提交。
- `frontend/src/api/` 补充模型管理 API 封装与类型。

## Constraints

- 模型 registry 保持现有文件式方案（`models/` + `active.json`），不迁数据库。
- 算法集合维持 random_forest / xgboost，不新增算法。
- 依赖 07-07-admin-data-collect 的 job_runner 与 admin_job 表，须在其后实施。

## Acceptance Criteria

- [ ] 发起训练接口立即返回 job id，训练在后台执行（期间其他 API 正常响应），任务状态从 running 到 success 可通过轮询观察。
- [ ] 训练完成后版本表出现新版本（版本号自增、含指标），活跃指针不变；手动切换活跃后 `GET /predict/{region_id}` 使用新模型（meta 中模型名可验证）。
- [ ] 训练进行中再次提交训练返回 409，前端按钮禁用。
- [ ] 模型管理页在浏览器中完整走通：查看列表 → 训练 → 进度 → 刷新 → 切换活跃。
- [ ] 新增/改动端点有 pytest 用例（train_model 打桩，验证任务流转与互斥；切换活跃持久化）。
