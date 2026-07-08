# ML 使用：预测覆盖与置信区间

## Goal

预测覆盖面从「月度历史 ≥12 个月的少数城市」扩大到 330 年度城市（带数据质量
标注与降级说明）；置信区间在不同价位城市下均合理；prediction 表不残留旧版本行。

## Requirements

- R1 预测取数走 ml-dataset-builder 的多源序列构建器：仅有年度数据的城市用
  「校准+插值」序列预测；响应新增 `data_quality` 字段
  （`monthly` | `annual_interp` | `mixed`）说明依据数据的口径。
- R2 前端预测页展示数据质量标注（年度插值城市显示「基于年度挂牌数据推算」
  一类提示），风格沿用走势图已有的「年度·挂牌」口径标签。
- R3 置信区间相对化：residual 策略改为相对残差
  `margin = 1.96 × resid_std_pct × y_hat`；meta 新增 `resid_std_pct`，旧 meta 只有
  绝对 `resid_std` 时沿用旧算式（兼容）。
- R4 prediction 表治理：同 (region, model_name) 写入新预测时删除其它
  model_version 的旧行；表中只保留每模型最新版本的预测。
- R5 年度插值序列预测的置信区间放大：`data_quality=annual_interp` 时 margin 乘
  惩罚系数（初始 1.5，常量），并在响应与前端透出。

## Acceptance Criteria

- [ ] 选一个仅有 listing_annual_58 数据的城市：预测返回 200 + `annual_interp`
      标注 + 放大的区间（此前 404）
- [ ] 北京（混合源）：预测返回 `mixed`，序列 2018-2024 缺口由年度校准值补齐
- [ ] creprice 城市（如泉州区县）：行为与现状一致，`data_quality=monthly`
- [ ] 用旧模型（无 resid_std_pct）预测不报错，区间退回绝对残差算式
- [ ] 写入新版本预测后，同 region 旧版本行被清理（DB 验证）
- [ ] 前端 build 通过，预测页可见标注

## Notes

- 依赖 ml-dataset-builder（序列构建器）。
- 历史仍不足模型窗口的区域继续 404，文案不变——覆盖扩大靠数据，不靠放宽
  MIN_HISTORY_MONTHS。
