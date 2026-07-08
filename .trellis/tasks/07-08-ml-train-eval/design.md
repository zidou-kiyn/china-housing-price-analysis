# 设计：训练评估与可复现

## 改动面

全部集中在 `backend/app/ml/train.py` + `app/schemas/predict.py` +
`api/v1/predictions.py`（透出）。无 DB 变更。

## 基线（train.py 内纯函数）

```python
def _baseline_metrics(frame_val: pd.DataFrame) -> dict:
    # last_value: y_hat = lag_1 列
    # seasonal:   y_hat = lag_12 列（模型窗口 n_lags >= 12 时才有；否则省略）
    return {"last_value": {"mae": ..., "mape": ...},
            "seasonal": {...} | None}
```

验证集与模型用同一后 20% 切分，可直接从特征列取 lag 值，无需重算序列。
`beats_baseline = metrics.mape < baselines.last_value.mape`。

## RF 网格

`RF_GRID = {"n_estimators": (100, 300), "max_depth": (10, None)}`，复用现有
`_fit_xgboost` 的 CV 骨架——抽出通用 `_grid_search_cv(estimator_cls, grid, x, y)`，
RF/XGB 共用（消重复）。sample_weight（dataset-builder 引入）在 CV 折内同步切片。

## meta 新字段（只增）

```json
{
  "baselines": {"last_value": {...}, "seasonal": {...}},
  "beats_baseline": true,
  "per_region_metrics": {"regions": 28, "median_mape": 2.1,
                          "worst": [{"region_type": "district", "region_id": 3, "mape": 8.2, "samples": 4}]},
  "dataset": {"per_source": {...}, "ratio_curve": {...}, "fingerprint": "abc123..."}
}
```

`ModelVersionOut` 新增 `beats_baseline: bool | None`、`baseline_mape: float | None`
（取 last_value.mape），旧 meta 缺字段时为 None——Pydantic 可选字段天然兼容。

## 分区域评估

验证集 frame 保留 region_type/region_id 列（已有 `region_id`，`region_type_enc`
可反查），groupby 后逐组 `_mape`；样本 <2 的组仍计入但标注 samples。

## 权衡

- 基线只做评估参照、不做可切换的"预测模型"：避免 ModelStore 引入非 sklearn
  对象的特殊分支。
- worst 取 5 个足够定位问题区域，避免 330 城时 meta 膨胀。
