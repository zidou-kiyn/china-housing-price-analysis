# 设计：多源训练集构建器

## 边界与模块

新增 `backend/app/ml/dataset.py`，职责：DB 快照行（分源）→ 校准/扩充后的
`RegionSeries` 列表 + `DatasetMeta`。`features.py` 只做序列→特征矩阵，不再感知
多源；`train.py` 只做训练，不感知取数。

```
predictions.py(_load_snapshot_rows 改造)
   └─ dataset.build_multi_source_series(rows_by_source)  ← 新
        ├─ 月度源: features.build_region_series(现有逻辑)
        ├─ 年度源: _annual_to_monthly(逐年比值校准 + 线性插值)
        └─ 合并去重(真实月度优先) → (list[RegionSeries], DatasetMeta)
```

## 数据流与契约

### 取数（分源）

`select_source_snapshots(session, region_type, region_ids) -> dict[source, list[row]]`
新增于 `app/services/price_select.py`（读取层唯一入口约定），普通 select 按
source 分组返回，不做 DISTINCT ON 合并。既有 `select_merged_snapshots` 不动
（走势/排行/对比继续用）。

### RegionSeries 扩展

`features.RegionSeries` 增加两个带默认值的字段（向后兼容）：

```python
basis: str = "listing"            # listing | transaction
weights: list[float] | None = None  # 与 prices 等长; None=全 1
interp_flags: list[int] | None = None  # 1=年度插值点
```

### 特征列（新版）

`feature_columns(n_lags)` 追加 `basis_enc`、`is_annual_interp` 两列（追加在尾部，
旧模型 meta.features 不含它们，推理时按 meta.features 取列即可兼容——见
predict.py 的 `build_inference_row(...)[feature_columns]` 调用点，需改为按
meta.features 切片）。

### 口径校准（逐年分段比值）

```python
def estimate_basis_ratio_curve(rows_by_source) -> dict[str, float]:
    # 找 (region, month) 同月同区域的 transaction 月度 vs annual listing 对
    # 按年份聚合 median(transaction/listing) → {"2010": 0.792, ..., "2017": 1.085}
```

应用：年度挂牌价 × ratio(year)；year 超出曲线范围取最近端点年的比值。
曲线、样本对数、应用行数全部进 DatasetMeta。北京当前 8 对是唯一来源，
未来新增重叠源自动扩大样本。

### 年度→月度插值

年度源每城约 15 个 12 月点：先按年校准，再 12 月点间线性插值成连续月序列
（`pd.Series.interpolate`，首点前不外推）。所有点 `interp_flags=1`（12 月真实点
也标 1——它是年度口径，非月度行情），`weights=ANNUAL_SAMPLE_WEIGHT=0.3`。

### 合并去重

同一 (region_type, region_id) 若月度源与年度源都产出序列：按月拼接，重叠月取
月度真实值（weight=1, flag=0），仅缺口月用年度插值填。产出单一 RegionSeries，
月份连续性由两段序列的并集重建（中间仍缺 → 线性插值，缺口段 flag=1、降权）。

### DatasetMeta

```python
@dataclass
class DatasetMeta:
    per_source: dict[str, {"rows": int, "regions": int, "min_month": str, "max_month": str}]
    ratio_curve: dict[str, float]
    ratio_pairs: int
    calibrated_rows: int
    fingerprint: str  # sha256(排序后 region:month:price 拼接)[:16]
```

## 训练侧接线

- `build_training_frame` 透传 `weight` 列；`train_model` 提取为 `sample_weight`
  传入 `model.fit(x, y, sample_weight=w)`（RF/XGB 均原生支持）。
- `train_model` 增加可选参数 `dataset_meta`，写入模型 meta（供 ml-train-eval 用）。

## 权衡与备选

- **不用单一折价系数**（HANDOFF 原案）：实证比值 0.79→1.09 漂移，单值会给早年
  数据注入 ~20% 系统偏差。逐年分段最简单且忠于数据。
- **不做跨城池化独立年度模型**（HANDOFF 提到的方向之一）：本轮先用"校准+插值
  +降权"统一进月度模型，池化模型是后续任务（复杂度高、收益未证）。
- **12 月真实年度点也降权**：它是年度挂牌口径，与月度行情不同质；如果不降权，
  330 城 × 15 点会淹没 396 行真实月度样本。

## 兼容与回滚

- 旧模型加载/预测不受影响：推理特征按模型 meta.features 构造。
- `ANNUAL_SAMPLE_WEIGHT=0`（或过滤 flag）即可退化回纯月度训练集，回滚无需迁移。
- 无 DB schema 变更、无迁移。
