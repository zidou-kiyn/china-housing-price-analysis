# 执行计划——训练白名单与模型清理

## 顺序

### A. 白名单（代码，可测）
1. `app/core/source_policy.py`：加 `TRAINING_SOURCES=("creprice",)` +
   `training_rows_only(rows_by_source)` 纯函数。
2. `app/api/v1/predictions.py::_load_source_rows`：返回前套 `training_rows_only`。
3. `app/services/data_quality.py::_compute_data_fingerprint`：build 前套
   `training_rows_only`（不动审计各节的取数）。
4. 测试：新增 `tests/core/test_source_policy.py`（或并入既有）测 `training_rows_only`
   只保留 creprice；确认 `test_dataset.py` 多源用例仍全绿（构建器未改）。

**验证 A**：`docker compose exec backend uv run pytest tests/ml tests/services
tests/core -q`。

### B. 空窗兜底（代码，可测）
5. `app/api/v1/predictions.py::get_prediction`：无活跃模型分支改
   `ApiError(404, "预测功能数据积累中，暂无可用模型…", "NO_ACTIVE_MODEL")`。
6. `frontend/src/views/PredictView.vue`：catch 读 `error.response?.data?.code`，
   NO_ACTIVE_MODEL → 友好空态文案。
7. 校验 `DataManageView.vue` 的 FRESHNESS_LABELS 含 "unknown"（缺则补）。
8. 测试：预测 API 空窗（tmp store 无模型）断言 404+code；质量报告无模型断言
   status=="unknown" 且不 500。

**验证 B**：`pytest tests/api/test_predict.py tests/api/test_admin_data_quality.py -q`
+ `npm run build`。

### C. 破坏性清理（本地状态，最后做、可核验）
9. 清空 prediction 表：容器内 `DELETE FROM prediction`，验证 count==0。
10. 删全部模型：`backend/models/{random_forest,xgboost}/*`、`models/active.json`、
    `backend/models.bak-governance/`；保留空 `models/` 目录。
11. 运行时验证：`GET /api/v1/predict/<qz区县>`（登录态）→ 404 NO_ACTIVE_MODEL；
    `GET /admin/data-quality/report` → 200 且 model_freshness.status=="unknown"；
    PredictView 页面显式"数据积累中"空态；前端预测入口在 creprice 下不再进得去有效预测
    （返回空窗态，不 500）。

### D. 留档（R5）
12. 回填 prd/notes：v1.8 重训前置 = full-data-crawl 完成；更新
    `.trellis/spec/backend/database-guidelines.md` §ML training-data path（白名单口径）。

## 审查门 / 回滚点
- 门 1（A+B 完成、全绿）：提交代码（白名单 + 空窗）。
- 门 2（C 完成、运行时验证过）：破坏性清理是本地状态，无代码提交；记录到 journal/notes。
- 回滚：白名单扩容即恢复多源；模型/预测删除不可逆（父任务已授权，无需再确认）。

## 完成校验（对齐 prd Acceptance）
- [ ] 白名单单测：混合源取数 → 训练集只含 creprice
- [ ] `backend/models/` 无模型文件、无 active.json；prediction 表 0 行
- [ ] 预测页显式空窗；预测 API 无活跃模型 404+NO_ACTIVE_MODEL、不 500
- [ ] 质量报告无模型正常产出（新鲜度 unknown 降级）
- [ ] 全量 pytest + 前端 build 通过
