# M2-5 技术设计

## 模块划分（backend/app/ml/）

| 文件 | 职责 |
|------|------|
| `features.py` | `build_feature_frame(rows, n_lags)`：快照行 → 特征 DataFrame（插值、lag、rolling、变化率、季节、编码）；`FEATURE_ORDER(n_lags)` 生成列顺序；`build_inference_row(series, n_lags, target_month)` 推理特征 |
| `train.py` | `train_random_forest(snapshots, n_lags=None)`：自适应 lag 窗口 → 时序切分 → 训练 → 指标 → `save_model` 版本化落盘；`ModelStore`（models 目录扫描/加载/下一版本号） |
| `predict.py` | `rolling_predict(model, meta, series, months_ahead)`：滚动多步预测 + 树间方差置信区间 |

- pandas 装配特征，joblib 序列化，`models/` 根目录由 `settings.model_dir`（默认 `backend/models`）配置，测试注入 tmp_path。
- 编码：region label 编码用 `region_type*1e6+region_id`？→ 不做 hash 技巧，直接 `region_type_enc`（city=0/district=1）+ `region_id` 本身作为特征（树模型可用）。city_code one-hot 省略（单城市场景无增益，meta 记录训练城市范围）。

## 特征装配细节

1. 按 (region_type, region_id) 分组，month 索引重建连续月序列，supply_price 线性插值（`Series.interpolate`），首尾 NaN 不外推。
2. 缺失率（插值前 NaN / 总月数）> 30% 的区域跳过。
3. 组内特征：lag_i = shift(i)；rolling_mean_w = shift(1).rolling(w).mean()（避免泄漏当月值）；rolling_std_6 同理；mom_pct/yoy_pct 由 shift(1)/shift(12) 计算（同样不含当月）。
4. 标签 y = 当月 supply_price；dropna 后得样本。
5. month/quarter 从 year_month 解析。

> 注意：rolling/mom/yoy 全部基于 shift 后序列，保证特征只含 t-1 及更早信息，推理时可用「已知历史+已预测值」构造。

## 滚动推理

```
series = 区域插值后的月度价格列表（含历史）
for step in 1..months_ahead:
    x = build_inference_row(series, n_lags, next_month)
    per_tree = [est.predict(x) for est in model.estimators_]
    y_hat = mean(per_tree); ci = 1.96 * std(per_tree)
    series.append(y_hat)  # 回填供下一步 lag 使用
```

- `next_month` 递推自数据最新月。
- upsert prediction：`INSERT ... ON CONFLICT (region_type, region_id, target_month, model_name, model_version) DO UPDATE`（对应 uq_prediction_region_model）。

## 版本与 meta

- 目录扫描 `v*.pkl`，次版本 +1（v1.0 → v1.1）；meta JSON 与 docs/06 §8.2 对齐（含 n_lags、features、metrics、training_samples、city_codes、trained_at）。
- 推理默认加载最高版本（活跃版本切换 API 留 M3-1）。

## API 层

- `app/api/v1/predictions.py`：两个端点；schemas `app/schemas/predict.py`。
- GET /predict/{region_id}：查区域名（city/district 表）→ 载模型（无 → 404 PREDICTION_NOT_FOUND）→ 查该区域快照（不足 12 个月 → 404 PREDICTION_NOT_FOUND）→ 滚动推理 → upsert → 返回。DB 会话执行 upsert 后 commit。
- POST /admin/predict/train：加载快照（可选 city_code 过滤该市 city+district 区域）→ train → 202。
- 训练/推理为 CPU 同步计算，跑在 FastAPI async 端点内用 `run_in_executor`? 数据量小（<100 样本、100 棵浅树），毫秒级——直接同步调用可接受，不做线程池调度。

## 前端

- `api/predict.ts`：`fetchPrediction(regionType, id, monthsAhead)`。
- `PredictChart.vue`：x 轴 = 历史月 + 预测月；三个 series：历史实线、预测虚线（含衔接点）、置信区间用两条 stack line（lower + diff）areaStyle 填充；markLine 竖线标记预测起点。
- `PredictView.vue`：路由参数取 regionType/id；并行取走势（fetchTrend）与预测；404 时展示 el-empty 引导（提示训练或数据不足）。
- RankView 区县榜行尾加「预测」router-link（city 榜不加，MVP 只对 district 提供入口；city 预测 API 可用但无页面入口）。

## 测试

- `tests/ml/test_features.py`：合成 24 个月线性序列 → 校验 lag/rolling/mom/yoy 数值、无泄漏（特征不含当月值）、缺失率跳过。
- `tests/ml/test_train_predict.py`：合成 60 个月带季节性+噪声的 3 区域数据 → 训练 R²≥0.85、meta 落盘、rolling_predict 长度/区间合法（lower ≤ pred ≤ upper）、版本自增。
- `tests/api/test_predict.py`（slow）：admin train 真实库 → user 取泉州区县预测 3 个月 → prediction 表有记录；未登录 401；区域不存在 404。
