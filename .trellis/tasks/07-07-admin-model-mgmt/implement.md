# 管理端模型管理 — 执行计划

前置：07-07-admin-data-collect 已交付 job_runner、admin_job 表与 `GET /admin/jobs` 查询端点。

## Part 1：后端训练任务化（可独立提交）

- [ ] `POST /admin/predict/train` 改为 submit train 任务（`asyncio.to_thread` 包 train_model），返回 job_id
- [ ] 训练结果/指标写 admin_job.result；确认 `ModelVersionOut` 含 trained_at/metrics，缺则补
- [ ] pytest：train_model 打桩验证任务流转、互斥 409、失败置 failed；models list/active 既有用例回归
- 验证：`docker compose exec backend uv run pytest` 通过；手动 curl 提交训练（qz 小数据）观察 job 流转与新版本产出

## Part 2：前端模型管理页（可独立提交）

- [ ] API 封装 + 类型（版本列表/切换活跃/提交训练/任务轮询）
- [ ] 抽取 `useJobPolling` composable（与 DataManageView 共用，若彼处未抽则此处抽并回改）
- [ ] `views/admin/ModelManageView.vue` + 路由 `/admin/models` + AppHeader 菜单项
- [ ] E2E：模型页加载版本列表、切换活跃、提交训练出现进行中状态（训练可打桩或用最小数据真跑）
- 验证：`npm run lint && npm run type-check && npm run test:e2e`；浏览器手动走查完整闭环

## 完成门槛

- [ ] prd.md 验收标准逐条勾验（含切换活跃后预测接口生效验证）
- [ ] 后端全量 pytest + 前端 lint/type-check/e2e 全绿
