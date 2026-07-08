# 设计：预测覆盖与置信区间

## 数据流

```
GET /predict/{region_id}
  └─ dataset.build_multi_source_series(单区域)   ← 复用 ml-dataset-builder
       → RegionSeries(带 interp_flags/basis)
  └─ rolling_predict(model, meta, series, ...)
       → data_quality = mixed if flags 含 0 和 1；annual_interp if 全 1；monthly if 全 0
       → margin ×= ANNUAL_CI_PENALTY(1.5) when annual_interp
```

`_load_snapshot_rows` 被构建器调用替换后，predictions.py 的训练与预测两条路径
取数逻辑合一。

## 契约变更

- `PredictionResponse` 新增 `data_quality: str`（monthly|annual_interp|mixed）。
- `rolling_predict` 返回 `(points, data_quality)` 或 PredictionPoint 增设字段——
  选前者，保持 point 结构不动。
- meta 新增 `resid_std_pct = std((y_val - y_pred) / y_val)`；predict 时
  `resid_std_pct` 存在 → 相对区间，否则旧绝对区间。RF per_tree 策略天然随价位
  缩放，不动。

## prediction 表治理

写入循环前执行：
```sql
DELETE FROM prediction
 WHERE region_type=:rt AND region_id=:rid AND model_name=:m AND model_version != :v
```
同事务内先删后插，无迁移、无新约束。历史版本预测无读取方（前端只显示实时
响应），残留行是纯垃圾。

## 前端（PredictView.vue）

- 响应 `data_quality != 'monthly'` 时在结果卡片头部加 `el-tag`：
  `annual_interp` → 「年度挂牌推算」warning 色；`mixed` → 「混合口径」info 色，
  tooltip 说明区间已放大/数据构成。复用走势图口径标签的文案风格。

## 来自 dataset-builder 质检的强约束

- 预测侧构造序列时**必须复用模型 meta["dataset"]["ratio_curve"]**，禁止重估
  （否则训练/推理校准不一致）。
- basis_enc 训练/推理偏差：训练时北京 series 级 basis=transaction，预测路径改走
  构建器后须保证同一区域推理时 basis 与训练一致（由构建器统一产出即自然满足，
  勿在预测层另行默认 listing）。

## 权衡

- 惩罚系数 1.5 是保守初值（年度插值序列自相关高、真实波动被抹平，区间必然
  低估）；后续可用回测校准，本轮不做。
- 不放宽 MIN_HISTORY_MONTHS=12：年度城市校准后有 ~15 年月度插值序列，远超
  窗口，无需放宽；仍不足者是数据真缺，404 正确。
