# M2-5 ML 管线与预测 API

## Goal

交付 RandomForest 预测链路：特征工程 → 训练/评估/版本化 → 滚动推理（含置信区间）→ 预测 API → 前端 PredictView。

## Requirements

### 特征工程（docs/06 §3）

- 输入：price_snapshot（region_type + region_id + year_month + supply_price）。
- 特征：lag_1~lag_N（默认 N=12）、rolling_mean_3/6/12、rolling_std_6、mom_pct、yoy_pct、month、quarter、region_type 编码、region label 编码。
- 缺失月线性插值（单区域缺失率 >30% 跳过该区域）；装配后 dropna。
- **样本自适应**：真实数据尚少（district 仅 13 个月），训练时按 N=12→6→3 依次尝试，取首个样本数 ≥20 的窗口，实际窗口记入模型 meta。

### 训练（docs/06 §4~6）

- `RandomForestRegressor(n_estimators=100, max_depth=10, min_samples_split=5, random_state=42)`。
- 时序切分：按 year_month 排序后 80/20 训练/验证。
- 指标：MAE、RMSE、MAPE、R²，记入 meta。
- 版本化：`models/random_forest/v{major.minor}.pkl` + `v{x}_meta.json`（版本自增，meta 含特征列表/指标/样本数/训练时间/lag 窗口/城市范围）。模型目录不入 git。

### 推理（docs/06 §7）

- 加载最新版本模型（joblib），装配目标区域最新特征，逐月滚动预测 1~months_ahead 个月（预测值回填 lag 后继续）。
- 置信区间：RF 各棵树预测值 均值 ±1.96×标准差。
- 结果 upsert 进 prediction 表（region + target_month + model_name/version 唯一）。
- 历史数据 <12 个月的区域不生成预测。

### API（docs/05 §3.6）

- `GET /predict/{region_id}?region_type=&months_ahead=`（默认 3，user+）：即时推理并落库，返回 `{region_type, region_id, region_name, model_name, model_version, predictions: [{target_month, predicted_price, confidence_lower, confidence_upper}]}`。
  - 无已训练模型或区域数据不足 → 404 `PREDICTION_NOT_FOUND`（detail 说明原因）。
  - 区域不存在 → 404 `REGION_NOT_FOUND`。
- `POST /admin/predict/train`（admin）：请求 `{model_name: "random_forest", city_code?}`，同步训练，202 返回 `{message, model_name, model_version, metrics, training_samples}`。

### 前端

- PredictView（`/predict/:regionType/:id`，requiresAuth）：PredictChart 展示历史实线 + 预测虚线 + 置信区间阴影 + 今昔分界 markLine；页头显示模型名/版本。
- 入口：RankView 区县榜每行「预测」链接；数据不足时页面展示引导提示。

## 约束

- 真实数据（泉州 13 个月）能跑通全链路即可；模型质量达标线（R²≥0.85 等）用合成时序数据在单元测试中验证链路正确性，不作为真实数据验收标准（与父任务 PRD 一致）。
- 训练为同步执行（数据量小，秒级完成）；后台任务化留给 M3。
- `backend/models/` 加入 .gitignore。

## Acceptance Criteria

- [ ] POST /admin/predict/train 用真实库数据训练成功并产出版本化模型与 meta
- [ ] GET /predict/{泉州某区县}?region_type=district 返回 3 个月预测 + 置信区间，且写入 prediction 表
- [ ] 数据不足区域与未训练场景返回 404 语义化错误
- [ ] 合成数据单元测试：特征列正确、滚动预测长度正确、R² ≥ 0.85、置信区间包含点预测
- [ ] 前端 /predict 页渲染历史+预测+区间阴影，游客访问跳登录
- [ ] 后端 pytest 全绿、ruff 通过；前端 type-check/build 通过 + 浏览器实测
