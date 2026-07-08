# ML 训练：评估与可复现

## Goal

让训练指标可信、可对比、可复现：naive 基线对照、RF 交叉验证、分区域评估、
训练数据指纹入 meta。

## Requirements

- R1 naive 基线：训练时在同一验证集上计算两个基线的 MAPE/MAE——
  `last_value`（预测=上月值，即 lag_1）与 `seasonal`（预测=12 个月前值，序列不足
  12 个月时省略）；写入 meta.baselines，模型必须能与基线直接对比。
- R2 RF 交叉验证：RF 走与 XGB 相同的小网格 × TimeSeriesSplit 选参
  （n_estimators/max_depth 各 2 档），样本不足 MIN_CV_SAMPLES 时退默认参数，
  cv 信息记入 meta（消除 `cv: null`）。
- R3 分区域评估：验证集按 region 分组算 MAPE，meta 记录
  `per_region_metrics`：区域数、最差 5 个区域（region_type/id/MAPE/样本数）、
  MAPE 中位数。
- R4 数据指纹：训练 meta 并入 dataset-builder 产出的 DatasetMeta
  （per_source 分布、ratio_curve、fingerprint），实现训练可审计、可复现。
- R5 模型管理 API `GET /admin/predict/models` 透出 baselines 对比结果
  （schema 新增可选字段，不破坏旧 meta）。

## Acceptance Criteria

- [ ] 新训模型 meta 含 baselines（last_value 必有；样本够时含 seasonal）、
      cv（RF 不再为 null，样本足够时）、per_region_metrics、dataset 指纹
- [ ] 旧版本模型 meta（无新字段）在 list/predict 全链路不报错
- [ ] 单测覆盖：基线计算、RF 网格选参路径、分区域指标、meta 兼容
- [ ] 全量测试通过

## Notes

- 基线不落盘为"模型"，只是评估参照；若模型 MAPE 高于 last_value 基线，训练
  结果照常保存但 meta 标记 `beats_baseline: false`（管理页可显示，不阻断）。
- 依赖 ml-dataset-builder 的 DatasetMeta（R4）；若先行实施，R4 留待接线。
