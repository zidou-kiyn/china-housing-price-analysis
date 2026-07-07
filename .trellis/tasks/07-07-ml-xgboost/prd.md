# M3-1 XGBoost 调优与模型版本切换

## Goal

在 M2-5 RF 预测链路之上：支持 XGBoost 训练（含时序交叉验证调参）、RF/XGB 指标对比、以及「活跃模型版本」切换 API，使预测端点可在两种模型间无感切换。

## Requirements

### XGBoost 训练

- `POST /admin/predict/train` 的 `model_name` 扩展为 `random_forest | xgboost`，共用现有特征工程与自适应 lag 窗口逻辑。
- XGBoost 用时序交叉验证（expanding window，`TimeSeriesSplit`）在小网格上调参（n_estimators/max_depth/learning_rate），以 MAPE 为选优指标；样本 < 30 时跳过 CV 用默认参数（meta 记 `cv: null`）。
- CV 结果（折数、best_params、各折 MAPE）与最终 holdout 指标一并写入模型 meta。
- 版本化目录复用 ModelStore：`models/xgboost/v{x}.pkl + v{x}_meta.json`。

### 置信区间

- RF 保持现状（各树预测 ±1.96σ）。
- XGBoost 无 `estimators_` 逐树接口：训练时把 holdout 残差标准差 `resid_std` 写入 meta，推理时用 `预测值 ±1.96×resid_std`。
- `rolling_predict` 按 meta 的 `ci_strategy`（`per_tree` / `residual`）分派；旧版 RF meta 无该字段时默认 `per_tree`。

### 模型对比与版本切换 API

- `GET /admin/predict/models`（admin）：列出所有模型全部版本（model_name、version、trained_at、metrics、training_samples、is_active），指标并排即为 RF/XGB 对比。
- `PUT /admin/predict/models/active`（admin）：`{model_name, version}` 设为活跃模型；模型或版本不存在 → 404。
- 活跃指针持久化在 `models/active.json`；`GET /predict/*` 改用活跃模型，未设置活跃指针时回退「random_forest 最新版」（与 M2-5 行为兼容）。

## 约束

- 真实数据（泉州 13 个月）只需跑通链路；模型质量达标线用合成数据单元测试验证（与 M2-5 一致）。
- 训练仍同步执行（数据量小）；后台任务化不在本任务范围。
- 新依赖 `xgboost` 加入 pyproject（CPU 版即可）。

## Acceptance Criteria

- [x] POST /admin/predict/train {"model_name":"xgboost","city_code":"qz"} 训练成功，meta 含 CV 结果与 resid_std
- [x] 合成数据单元测试：XGB R² ≥ 0.85，且 XGB MAPE ≤ RF MAPE（同一合成数据集对比）
- [x] GET /admin/predict/models 返回两种模型的版本与指标，is_active 标记正确
- [x] PUT 切换活跃模型后，GET /predict/{region} 返回的 model_name/version 随之变化；切回 RF 亦然
- [x] 未设置 active.json 时预测行为与 M2-5 兼容（random_forest 最新版）
- [x] 后端 pytest（单元 + slow）全绿、ruff 通过
