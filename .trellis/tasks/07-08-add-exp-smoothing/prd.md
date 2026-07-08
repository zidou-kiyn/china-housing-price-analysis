# 新增 ExponentialSmoothing 模型

## Goal

在现有 RandomForest / XGBoost 旁新增 ExponentialSmoothing 算法选项，为短时序数据（13 个月）提供更合适的预测模型。

## Background

RF/XGBoost 是横截面模型，对 lag_12/yoy 等特征需要长时序支撑。ES 是纯时序模型，专为短序列设计，13 个月数据即可给出有意义的趋势预测。

ES 与 RF/XGB 的根本区别：ES 按单条时间序列训练，因此一次"训练"会为每个区域（城市/区县）各产出一个拟合模型，打包存储在一个 pkl 文件中。

## Requirements

### R1: 训练
- 算法名称 `exp_smoothing`，与 `random_forest` / `xgboost` 并列
- 训练时遍历所有区域（城市+区县），对每个区域的月度价格序列拟合 `statsmodels.tsa.holtwinters.ExponentialSmoothing`
- 数据点不足（< 6 条）的区域跳过，记录日志
- 所有区域的拟合模型打包为 `dict[tuple[str,int], fitted_model]`（key = (region_type, region_id)）
- 整体序列化为一个 pkl 文件，复用 ModelStore 版本管理

### R2: 评估
- 对每个区域做时序 80/20 分割评估（数据足够时）
- 汇总指标：全局 MAE/RMSE/MAPE，以及 worst-5 区域明细
- 指标格式与 RF/XGB 的 `_meta.json` 保持一致

### R3: 预测
- `predict/{region_id}` 端点检测 active 模型类型
- 如果是 ES，从 dict 中按 (region_type, region_id) 取子模型
- 调用 ES 的 forecast 方法生成多步预测
- 如果该区域不在 dict 中，返回 "该区域暂无预测数据"

### R4: UI
- 训练页面算法下拉新增 "指数平滑 (Exponential Smoothing)" 选项
- 训练结果展示与 RF/XGB 一致（指标、版本号）
- 预测页面无需改动（通过 active 模型自动路由）

### R5: 依赖
- 使用 `statsmodels`（项目中应已有，需确认）
- 不引入 Prophet / cmdstanpy 等重依赖

## Acceptance Criteria

- [ ] 训练页面可选择 exp_smoothing 算法
- [ ] 训练完成后 ModelStore 中有 `exp_smoothing/vX.Y.pkl` + `_meta.json`
- [ ] meta.json 包含 MAE/RMSE/MAPE 指标
- [ ] 设为 active 后，预测接口能返回 ES 预测结果
- [ ] 区域不在 ES dict 中时返回明确错误信息而非 500
- [ ] 现有 RF/XGB 训练和预测不受影响
- [ ] 现有测试通过
