# 技术设计——训练白名单与模型清理

## 边界

ML 侧落实 creprice-only：训练/预测取数按源白名单过滤；删全部旧模型 + 清空
prediction 表；无活跃模型时全链路优雅空窗。多源校准/赋形/插值代码路径**保留**
（不 revert，白名单挡在上游使其自然走不到，可逆）。

## 关键决策：白名单加在"装载入口"，不加在纯构建器

`build_multi_source_series`（`app/ml/dataset.py`）是纯函数，且其多源单测
（`test_dataset.py` 校准/赋形/合并）是"保留路径可逆"的活证据。若在构建器入口过滤，
这些单测会集体失效、且抹掉可逆性的验证。故白名单加在 **DB→dict 的装载边界**：

- `app/core/source_policy.py`：加 `TRAINING_SOURCES = ("creprice",)` +
  纯函数 `training_rows_only(rows_by_source: dict) -> dict`（滤掉非白名单源）。
- `app/api/v1/predictions.py::_load_source_rows`（训练与预测共用）：返回前套
  `training_rows_only`。→ 训练集、预测取数都只含 creprice。
- `app/services/data_quality.py::_compute_data_fingerprint`：build 前套
  `training_rows_only`（指纹口径必须与训练一致，否则新鲜度永远 stale）。
  **审计各节**（overlap/direction/coverage）仍走未过滤的 `_load_source_rows`——
  审计要看全源，不受白名单影响。

构建器本身与其多源单测**零改动**，保留路径与可逆性完整。

## 模型清理（R2）

`backend/models/` 是 gitignore 的本地挂载目录（`./backend:/app`，`ml_model_dir="models"`）。
`load_active()` 在指针失效时**回退 random_forest 最新版**——故空窗必须删**全部**
pkl/meta，仅删 active.json 不够。操作：
- 删 `backend/models/random_forest/`、`backend/models/xgboost/` 下全部文件、`active.json`；
  保留空的 `models/` 目录（ModelStore 读空目录返回 None/[]，已验证 get_active/versions/
  list_all 都对不存在目录安全）。
- 删遗留快照目录 `backend/models.bak-governance/`（gitignore 本地目录）。
- 非代码/非 git 变更（目录已忽略），属本地状态清理；破坏性但父任务已锁定授权。

## 预测清理（R3）

`DELETE FROM prediction`（全表，均为多源模型产物，含 330 年度城市 annual_interp
插值预测）。经容器执行，验证 `SELECT count(*)==0`。

## 空窗兜底（R4）

- b) 预测 API（`predictions.get_prediction` 原 :91-93）：`load_active() is None` 时
  抛 `ApiError(404, "预测功能数据积累中，暂无可用模型（等全量采集完成后重训）",
  "NO_ACTIVE_MODEL")`（原为 PREDICTION_NOT_FOUND，语义细化 + 独立 code）。
- a) `PredictView.vue`：catch 中读 `error.response?.data?.code`，
  `=== 'NO_ACTIVE_MODEL'` → 友好空态文案（沿用既有 el-empty，description 换成
  "数据积累中，暂无可用模型"），其余错误维持原文案。不报错、不白屏。
- c) 质量报告新鲜度：`compute_model_freshness(None, ...)` 已返回
  `{status:"unknown", note:"无活跃模型"}`，`build_report` 已对 active_meta=None 安全；
  前端 `DataManageView` 的 `FRESHNESS_LABELS`/`freshnessTagType` 需确保含 "unknown"
  分支（多为既有，缺则补）。→ 服务层基本已满足，重点是验证 + 前端标签兜底。

## 重训触发留档（R5）
v1.8 重训前置 = 07-07-full-data-crawl 全量首采完成；届时新开任务：白名单生效下重训、
按治理流程激活。本任务仅在 prd/notes + spec 留档，不执行重训。

## 兼容与回滚
- 白名单：`TRAINING_SOURCES` 扩容即恢复多源训练；构建器路径完好。
- 模型/预测删除：不可逆（模型 gitignore、无备份保留），父任务 grilling 已明确授权。
- 现有测试：预测/模型测试均 monkeypatch `ml_model_dir` 到 tmp 自训（已核实），
  **不依赖** `backend/models/`，删真实模型不破坏测试。

## 测试策略
- 加 `training_rows_only` 单测：含 creprice+58+kaggle 的 dict → 只剩 creprice（R1 验收）。
- 预测 API 空窗：无活跃模型场景断言 404 + code=NO_ACTIVE_MODEL（tmp store 不训模型）。
- 质量报告无模型：断言 model_freshness.status=="unknown"、report 正常产出不 500。
- 全量 `pytest` 通过；前端 `npm run build` 通过。
