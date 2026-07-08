# Design — 多源数据源独立存储与口径治理

## 核心思想

**写入各存各的，读取按用途合并。** 冲突解决从"写入时 latest-wins"（有损、顺序敏感）移到"读取时按优先级选择"（无损、规则显式）。

## 1. Schema（迁移 005）

```
price_snapshot:
  - 回填 source IS NULL → 'creprice'（004 前唯一源）
  - source 改 NOT NULL
  - drop  uq_price_snapshot_region_month (region_type, region_id, year_month)
  - add   uq_price_snapshot_region_month_source (region_type, region_id, year_month, source)
```
- downgrade（有损）：按优先级保留每 (region,month) 最优行、删其余，再恢复旧约束。
- `price_distribution` 不动（当前仅 creprice 写入，出范围）。

## 2. 源策略单点定义 `app/core/source_policy.py`

```python
# 排序值小者优先；月度成交/评估 > 年度挂牌
SOURCE_PRIORITY = {"creprice": 0, "kaggle_lianjia": 1, "listing_annual_58": 2, "listing_annual_anjuke": 3}
SOURCE_META = {  # granularity + 口径，前端标签/接口透出用
  "creprice":            {"granularity": "monthly", "basis": "listing"},
  "kaggle_lianjia":      {"granularity": "monthly", "basis": "transaction"},
  "listing_annual_58":   {"granularity": "annual",  "basis": "listing"},
  "listing_annual_anjuke": {"granularity": "annual", "basis": "listing"},
}
def priority_order():  # SQLAlchemy CASE 表达式，供 DISTINCT ON 排序
```

## 3. 合并选择唯一入口 `app/services/price_select.py`

```python
async def select_merged_snapshots(session, region_type, region_ids=None) -> list[PriceSnapshot]:
    # PG: SELECT DISTINCT ON (region_id, year_month) ...
    #     ORDER BY region_id, year_month, <priority CASE>
```
调用方收敛到此入口：
- `prices.py /trend`（默认合并模式）
- `analytics.py _load_snapshots`（修复多源同月字典随机覆盖）
- `predictions.py _load_snapshot_rows`（防 ML 序列出现同月重复）

## 4. Loader

`upsert_price_snapshots` 冲突目标改新约束名；`source` 参数改必填 `str`（所有调用方已传）。

## 5. API

- `GET /prices/trend`：形状不变（list[TrendPoint]），改为合并选择后的结果 —— 兼容 Dashboard/Predict/Map/usePrice。
- `GET /prices/trend?split=true`：新增，返回 `list[TrendSeries]`：
  `TrendSeries{source, granularity, basis, points: list[TrendPoint]}`（按 SOURCE_PRIORITY 排序）。
  缓存 key 分开：`api:trend:{rt}:{id}` 与 `api:trend:split:{rt}:{id}`（已被 `api:trend:*` 失效模式覆盖）。
- `analytics` rank/compare 条目：已含/补充 `source` 字段，前端据此打口径标签。

## 6. 前端

- `HomeView`/`usePrice`：走势图改用 split 模式取数。
- `TrendLine`：接受 `series[]`；月度源=实线，年度源=虚线+加大 symbol，不跨源连线；图例按源标签（"禧泰 · 月度"/"链家 · 月度成交"/"58 · 年度挂牌"）；保留图下口径注释。district 走势同组件自动受益。
- 排行/对比视图：`source` 为年度挂牌时显示 `<el-tag>年度·挂牌</el-tag>`。
- Dashboard/Predict/Map 不改（吃合并后的默认 trend）。

## 7. 数据修复（迁移后执行）

1. 重跑 kaggle 导入（`PipelineRunner.run('kaggle_lianjia','bj')`）→ 北京 12 月成交行以 kaggle source 独立成行恢复。
2. 重跑 58 导入（幂等自检）。
3. 验证：北京 2016-12 存在两行（kaggle + 58）；`/prices/trend?split=true` 北京返回 ≥2 条 series。

## 8. 兼容与回滚

- 默认 trend 形状不变；merged 结果对纯 creprice 城市与改前一致（每月本就一行）。
- 回滚 = alembic downgrade（有损去重，保最优行）+ 还原代码。
- ML：本轮仅换取数入口，特征/训练逻辑不动；跨口径特征工程留给下一任务。
