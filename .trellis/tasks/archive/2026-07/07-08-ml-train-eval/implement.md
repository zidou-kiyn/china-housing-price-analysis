# 执行清单：训练评估与可复现

## 顺序步骤

### Step 1 — CV 骨架统一
- [x] 抽出 `_grid_search_cv`（TimeSeriesSplit × 网格 × sample_weight 折内切片）
- [x] `_fit_xgboost` 改用骨架；新增 `RF_GRID`，`_fit_random_forest` 接入

### Step 2 — 基线与分区域评估
- [x] `_baseline_metrics`（last_value/seasonal）；`beats_baseline` 判定
- [x] 验证集 groupby region 分组 MAPE → `per_region_metrics`
- [x] meta 并入 `dataset`（DatasetMeta，来自 ml-dataset-builder）
- [x] R6 分层：`metrics_real_monthly` + `validation_strata`（按 is_annual_interp）

### Step 3 — 透出与兼容
- [x] `ModelVersionOut` 新增可选 `beats_baseline`/`baseline_mape`
- [x] `list_models` 从 meta 读取（缺省 None）

### Step 4 — 测试
- [x] 单测：基线数值、RF cv 非 null、分区域指标、分层指标、旧 meta 兼容（无新字段照常 list）
- [x] 全量测试（287 passed）+ 训练冒烟（qz + 全库各一次，meta 新字段齐全）

## 验证命令

```bash
docker compose exec backend uv run pytest tests/ -x -q
```

## 回滚点

- 每 Step 独立可 revert；meta 只增字段，回滚不影响已训模型。

## 审查门

- Step 2 后核对：模型 MAPE 与基线在同一验证集（同切分、同样本）计算。
  （已核对：`_baseline_metrics`/`_per_region_metrics`/`_stratified_metrics` 全部
  基于 `frame.iloc[split:]`，与 `metrics` 用的 x_val/y_val 同一切分同一样本。）

## 冒烟记录（2026-07-08，临时目录训练，不入 models/）

- qz RF：MAPE 1.88（real_monthly 同值，无年度层）；last_value 基线 1.37 →
  `beats_baseline: false`（小样本 RF 打不过 naive，照常保存并标记）；cv 非 null。
- 全库 RF：全量 MAPE 0.25（验证集 6170/6247 为年度插值，偏乐观）；
  `metrics_real_monthly` MAPE 2.71 / MAE 322.79 / R² 0.9376 ≤5% 达标线 →
  `ANNUAL_SAMPLE_WEIGHT=0.3` 保持不动；last_value 基线 0.39、seasonal 6.04，
  `beats_baseline: true`；per_region 354 区域、median 0.13、worst 5.73。
