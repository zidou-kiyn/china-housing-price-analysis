# M3-1 执行计划

1. [x] pyproject 加 `xgboost` 依赖并安装（M2-5 已预埋 xgboost>=2,<3，venv 已装 2.1.4）
2. [x] `app/ml/train.py`：`train_model(algorithm, ...)` + XGB CV 调参 + meta 新字段 + ModelStore 活跃指针/list_all/load
3. [x] `app/ml/predict.py`：ci_strategy 分派
4. [x] `tests/ml/test_train_predict.py` 扩展 + `tests/ml/test_model_store.py`（合成数据）
5. [x] `app/schemas/predict.py` + `app/api/v1/predictions.py`：train 分派、models 列表、active 切换、predict 用活跃模型
6. [x] `tests/api/test_predict.py` 扩展（slow：训练→列表→切换→预测→切回）
7. [x] 验证：pytest 单元 53 绿 + slow 10 绿、ruff 通过；真实库训练 xgboost v1.0（CV 3 折选参）并实测切换往返
8. [x] spec 更新、提交、finish

## 验证结果（2026-07-07）

- 合成数据：XGB R²≥0.85 且 MAPE ≤ RF（链路正确性）。
- 真实数据（泉州 50 样本）：RF v1.0 MAPE 1.59 / XGB v1.0 MAPE 2.26 —— 小样本下 RF 更优，
  活跃模型保持 random_forest v1.0（这正是版本切换 API 的用途；数据积累后可重训重比）。

## 验证命令

```bash
cd backend && .venv/bin/python -m pytest tests/ml -q && .venv/bin/python -m ruff check app tests
cd backend && .venv/bin/python -m pytest tests/api/test_predict.py -m slow -q   # 需 DB/Redis
```

## 回滚点

- 步骤 2~4（纯计算层）与 5~6（API 层）解耦，可分步提交。
