# 执行清单：训练评估与可复现

## 顺序步骤

### Step 1 — CV 骨架统一
- [ ] 抽出 `_grid_search_cv`（TimeSeriesSplit × 网格 × sample_weight 折内切片）
- [ ] `_fit_xgboost` 改用骨架；新增 `RF_GRID`，`_fit_random_forest` 接入

### Step 2 — 基线与分区域评估
- [ ] `_baseline_metrics`（last_value/seasonal）；`beats_baseline` 判定
- [ ] 验证集 groupby region 分组 MAPE → `per_region_metrics`
- [ ] meta 并入 `dataset`（DatasetMeta，来自 ml-dataset-builder）

### Step 3 — 透出与兼容
- [ ] `ModelVersionOut` 新增可选 `beats_baseline`/`baseline_mape`
- [ ] `list_models` 从 meta 读取（缺省 None）

### Step 4 — 测试
- [ ] 单测：基线数值、RF cv 非 null、分区域指标、旧 meta 兼容（无新字段照常 list）
- [ ] 全量测试 + 训练冒烟（qz + 全库各一次，检查 meta 新字段）

## 验证命令

```bash
docker compose exec backend pytest tests/ -x -q
```

## 回滚点

- 每 Step 独立可 revert；meta 只增字段，回滚不影响已训模型。

## 审查门

- Step 2 后核对：模型 MAPE 与基线在同一验证集（同切分、同样本）计算。
