# M3-1 技术设计

## 改动面

| 文件 | 改动 |
|------|------|
| `app/ml/train.py` | `train_random_forest` 泛化为 `train_model(algorithm, ...)`；新增 XGB 参数网格 + `TimeSeriesSplit` CV；meta 增加 `ci_strategy`/`resid_std`/`cv`；ModelStore 增加 `active.json` 读写（`get_active/set_active/load_active`） |
| `app/ml/predict.py` | 置信区间按 `meta["ci_strategy"]` 分派：`per_tree`（现状）/ `residual`（±1.96×resid_std） |
| `app/schemas/predict.py` | TrainRequest.model_name pattern 放宽；新增 `ModelVersionOut`、`ActiveModelRequest` |
| `app/api/v1/predictions.py` | train 端点按 model_name 分派；新增 `GET /admin/predict/models`、`PUT /admin/predict/models/active`；GET /predict 改用 `load_active()` |
| `backend/pyproject.toml` | 新增 `xgboost` 依赖 |

## 训练层

```python
ALGORITHMS = {
    "random_forest": _fit_random_forest,   # 现有固定参数，不做 CV
    "xgboost": _fit_xgboost,               # 小网格 CV 调参
}

def train_model(algorithm, series_list, store, n_lags=None, city_codes=None) -> dict
```

- 自适应 lag 窗口、80/20 时序切分、`_evaluate` 指标均复用现状。
- `_fit_xgboost(x_train, y_train)`：样本 ≥ 30 时 `TimeSeriesSplit(n_splits=3)` 遍历网格
  `n_estimators ∈ {100, 300} × max_depth ∈ {3, 5} × learning_rate ∈ {0.05, 0.1}`（8 组 × 3 折），
  按各折平均 MAPE 选优；样本不足跳过 CV 用 `{300, 3, 0.05}` 默认组。返回 `(model, cv_info | None)`。
- meta 新字段：`ci_strategy`（rf=`per_tree`，xgb=`residual`）、`resid_std`（holdout 残差 σ，两种模型都算）、`cv`（xgb 专属，含 folds/best_params/fold_mapes）。
- `train_random_forest` 保留为 `train_model("random_forest", ...)` 的薄包装（现有测试/调用不破坏）。

## ModelStore 活跃指针

- `active.json`（`models/` 根目录）：`{"model_name": "...", "version": "..."}`。
- `set_active(name, version)`：校验 `versions(name)` 含该版本，否则 `ValueError`。
- `load_active()`：读指针 → `load(name, version)`；指针缺失/指向已删除文件时回退 `load_latest("random_forest")`（M2-5 兼容），仍无则 None。
- 新增 `load(name, version)` 与 `list_all() -> list[meta]`（扫描所有模型目录的 `v*_meta.json`）。

## 推理层

```python
if meta.get("ci_strategy", "per_tree") == "per_tree":
    per_tree = [tree.predict(x)[0] for tree in model.estimators_]
    y_hat, margin = mean(per_tree), 1.96 * std(per_tree)
else:
    y_hat = float(model.predict(x.to_numpy())[0])
    margin = 1.96 * meta["resid_std"]
```

滚动回填逻辑不变。XGBRegressor.predict 接受 numpy 数组，特征列顺序由 meta["features"] 保证一致。

## API 层

- `GET /admin/predict/models` → `list[ModelVersionOut]`：ModelStore.list_all() + active 指针标记。
- `PUT /admin/predict/models/active`：body `{model_name, version}`；ValueError → 404 `MODEL_NOT_FOUND`。
- `GET /predict/{region_id}`：`_store().load_active()` 替换 `load_latest("random_forest")`。
- `POST /admin/predict/train`：`train_model(payload.model_name, ...)`。

## 测试

- `tests/ml/test_train_predict.py` 扩展：同一合成数据集训练 rf + xgb → XGB R²≥0.85、XGB MAPE ≤ RF MAPE、meta 含 cv/resid_std/ci_strategy、residual 区间合法。
- `tests/ml/test_model_store.py`（新）：set_active/get_active/load_active 回退语义、list_all。
- `tests/api/test_predict.py` 扩展（slow）：训练 xgboost → 列模型 → 切换活跃 → GET /predict 返回 xgboost 版本 → 切回。
