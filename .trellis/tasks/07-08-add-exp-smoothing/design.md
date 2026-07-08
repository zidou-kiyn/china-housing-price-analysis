# 新增 ExponentialSmoothing 模型 — 技术设计

## 架构概述

ES 与 RF/XGB 的根本差异：ES 是单序列模型，不接受横截面特征。因此训练产物不是一个全局模型，而是 `dict[(region_type, region_id) → fitted_ES]`，整体打包为一个 pkl。

## 变更边界

### 1. `train.py` — 新增 ES 训练函数

```python
def _fit_exp_smoothing(series_list: list[RegionSeries], store: ModelStore, ...) -> dict:
    """为每个区域独立拟合 ES 模型，打包为 dict。"""
    models = {}
    skipped = []
    eval_results = []
    
    for rs in series_list:
        if len(rs.prices) < MIN_ES_SAMPLES:  # 建议 6
            skipped.append((rs.region_type, rs.region_id))
            continue
        # 80/20 时序分割
        split = max(int(len(rs.prices) * 0.8), 2)
        train_prices = rs.prices[:split]
        val_prices = rs.prices[split:]
        
        fitted = ExponentialSmoothing(
            train_prices, trend="add", seasonal=None,  # 13 个月不够一个完整季节周期
            initialization_method="estimated"
        ).fit(optimized=True)
        
        models[(rs.region_type, rs.region_id)] = fitted
        
        if val_prices:
            forecast = fitted.forecast(len(val_prices))
            eval_results.append({...})  # 收集评估指标
    
    # 汇总指标 + 序列化
    version = store.next_version("exp_smoothing")
    meta = {...}  # MAE/RMSE/MAPE 汇总 + worst-5 + skipped count
    store.save("exp_smoothing", version, models, meta)
    return meta
```

关键决策：
- `seasonal=None`：13 个月数据不足一个完整 12 月季节周期，启用 seasonal 会导致拟合不稳定
- `trend="add"`：捕捉线性趋势（房价通常有趋势性）
- 数据量 ≥ 6 条才训练（ES 最低需求）

### 2. `train.py` — ALGORITHMS 注册

ES 训练签名与 RF/XGB 不同（ES 需要 `series_list` 而非 `(x_train, y_train)`）。需要在 `train_model` 中分支处理：

```python
ALGORITHMS = {
    "random_forest": _fit_random_forest,
    "xgboost": _fit_xgboost,
}

def train_model(algorithm, series_list, store, ...):
    if algorithm == "exp_smoothing":
        return _train_exp_smoothing(series_list, store, ...)
    # 原有 RF/XGB 路径不变
    ...
```

### 3. `predict.py` — ES 预测分支

`rolling_predict` 当前直接用 sklearn model 的 `predict()` 方法。ES 模型用 `forecast()` 方法。

在 `predictions.py` 的 `get_prediction` 中需要检测模型类型并分支：

```python
model, meta = loaded
if meta["model_name"] == "exp_smoothing":
    # model 是 dict[(region_type, region_id) → fitted_ES]
    key = (region_type, region_id)
    if key not in model:
        raise ApiError(404, "该区域暂无预测数据（ES 模型未覆盖）", "PREDICTION_NOT_FOUND")
    es_model = model[key]
    forecast = es_model.forecast(months_ahead)
    points = [PredictionPoint(...) for val in forecast]
    data_quality = "monthly"
else:
    # 原有 RF/XGB 路径
    points, data_quality = rolling_predict(model, meta, series_list[0], months_ahead)
```

### 4. ES 置信区间

ES 的 `forecast()` 不直接给置信区间。使用训练集残差标准差估算：

```python
resid = train_prices - fitted.fittedvalues
resid_std = np.std(resid)
margin = 1.96 * resid_std
# 或使用相对残差（与 XGBoost 一致）
```

将 `resid_std` / `resid_std_pct` 存入 meta，预测时读取。

### 5. 前端 — 算法下拉选项

训练页面的算法选择下拉新增：
```
random_forest  →  随机森林 (Random Forest)
xgboost        →  XGBoost
exp_smoothing  →  指数平滑 (Exponential Smoothing)
```

### 6. `schemas/predict.py` — TrainRequest

`model_name` 的 pattern 校验需允许 `exp_smoothing`。当前 pattern 已支持（`^[a-z][a-z0-9_]{0,63}$`）。

## 数据流

```
训练:
  POST /admin/predict/train {model_name: "exp_smoothing"}
    └─ _run_train → _train_exp_smoothing(series_list, store)
         ├─ for region in series_list:
         │    ├─ 80/20 split
         │    ├─ ES fit
         │    └─ evaluate
         ├─ 汇总 meta (MAE/RMSE/MAPE)
         └─ store.save("exp_smoothing", version, dict_of_models, meta)

预测:
  GET /predict/{region_id}
    └─ load_active() → 检查 meta["model_name"]
         ├─ "exp_smoothing" → dict[key] → .forecast(months_ahead)
         └─ 其他 → rolling_predict() (不变)
```

## ModelStore 兼容性

ModelStore 对存储的对象类型无约束（joblib.dump 支持任意 Python 对象）。dict 类型与 sklearn model 一样可以 dump/load。`active.json` 指针、版本管理、cleanup 全部自动兼容。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 368 城 + N 区县 → 大 dict pkl 文件 | ES 模型很小（几个参数），即使 1000 个区域也仅 MB 级 |
| 部分区域数据不足 | skipped list 记入 meta，预测时 key 不存在返回 404 |
| seasonal=None 丢失季节性 | 数据积累到 2+ 年后可改为 seasonal="add", seasonal_periods=12 |
| ES fittedvalues 长度与输入不一致 | statsmodels ES 保证 fittedvalues 与输入等长 |
