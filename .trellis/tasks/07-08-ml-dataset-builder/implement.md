# 执行清单：多源训练集构建器

## 顺序步骤

### Step 1 — 取数与序列扩展
- [ ] `price_select.py` 新增 `select_source_snapshots`（分源返回，不合并）
- [ ] `features.RegionSeries` 增加 `basis`/`weights`/`interp_flags` 默认字段
- [ ] `feature_columns` 追加 `basis_enc`、`is_annual_interp`；`_feature_row` 产出两列
- [ ] `predict.py`/`train.py` 推理与训练取列改为按 meta.features 切片（旧模型兼容）

### Step 2 — dataset.py 构建器
- [ ] `estimate_basis_ratio_curve`：重叠对 → 逐年 median 比值曲线
- [ ] `_annual_to_monthly`：校准 + 12 月点线性插值 + flag/降权
- [ ] `build_multi_source_series`：月度/年度分流 → 合并去重（真实月度优先）→
      (series_list, DatasetMeta)
- [ ] `DatasetMeta` 指纹（sha256 前 16 位）

### Step 3 — 训练接线
- [ ] `build_training_frame` 透传 weight；`train_model` 传 `sample_weight`
- [ ] `train_model` 可选 `dataset_meta` 参数并入模型 meta
- [ ] `predictions._load_snapshot_rows`/`_run_train` 改走新构建器

### Step 4 — 测试与验证
- [ ] 单元测试：比值曲线（漂移数据）、年度插值、合并去重、权重透传、指纹、
      纯月度回归不变
- [ ] 容器内跑全量测试：`docker compose exec backend pytest`
- [ ] 冒烟：训练一次 RF，检查 meta 的 per_source 分布含 listing_annual_58

## 验证命令

```bash
docker compose exec backend pytest tests/ -x -q
docker compose exec backend python -c "…训练冒烟脚本…"
```

## 回滚点

- Step 2 独立文件，可整体删除回滚；Step 1/3 的接口改动均带默认值，逐个 revert 安全。

## 审查门

- Step 2 完成后自查比值曲线与验收边界（0.79~1.12）；Step 4 全绿后才进 commit。
