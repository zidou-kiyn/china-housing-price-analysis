# 新增 ExponentialSmoothing 模型 — 实施计划

## 检查清单

### Part 1: 依赖确认
- [ ] 确认 `statsmodels` 已在 `requirements.txt` / `pyproject.toml` 中
- [ ] 如未安装：添加 `statsmodels` 依赖

**验证**: `python -c "from statsmodels.tsa.holtwinters import ExponentialSmoothing"`

### Part 2: ES 训练函数
- [ ] `backend/app/ml/train.py`: 新增 `_train_exp_smoothing(series_list, store, dataset_meta)` 函数
- [ ] 遍历 series_list，每个区域拟合 ES（trend="add", seasonal=None）
- [ ] 数据 < 6 条的区域跳过
- [ ] 80/20 时序分割评估，收集 MAE/RMSE/MAPE
- [ ] 汇总指标：全局平均 + worst-5 区域
- [ ] 打包 dict[(region_type, region_id) → fitted_model]
- [ ] `store.save("exp_smoothing", version, models_dict, meta)`
- [ ] `train_model()` 函数中对 `algorithm == "exp_smoothing"` 分支到新函数

**验证**: 手动调用训练函数，检查 pkl 和 meta 生成

### Part 3: ES 预测
- [ ] `backend/app/api/v1/predictions.py` 的 `get_prediction`: 检测 `meta["model_name"] == "exp_smoothing"` 分支
- [ ] 从 dict 中按 `(region_type, region_id)` 取子模型
- [ ] 调用 `forecast(months_ahead)` 生成预测值
- [ ] 置信区间：使用 meta 中的 `resid_std_pct` 计算
- [ ] key 不存在时返回 404 + 明确错误信息
- [ ] 预测结果同样写入 Prediction 表

**验证**: set_active 为 ES 模型后，GET /predict/{region_id} 返回正确结果

### Part 4: 前端适配
- [ ] 训练页面算法下拉新增 `exp_smoothing` → "指数平滑 (Exponential Smoothing)"
- [ ] 确认训练结果展示（指标、版本号）与 RF/XGB 一致
- [ ] 模型列表页能正确显示 ES 模型版本

**验证**: 浏览器实测训练 + 预测流程

### Part 5: 测试
- [ ] 新增 ES 训练单元测试（mock 数据，验证 dict 结构和 meta 格式）
- [ ] 新增 ES 预测单元测试（key 存在 / key 不存在两种场景）
- [ ] 确认现有 RF/XGB 测试不受影响

**验证**: `pytest` 全通过

## 回滚方案

ES 是新增算法，不修改 RF/XGB 任何代码路径。回滚只需删除 ES 相关代码 + 从算法列表中移除。已训练的 ES 模型文件可通过 cleanup API 清理。
