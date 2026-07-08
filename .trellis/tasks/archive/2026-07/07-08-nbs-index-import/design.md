# 设计：NBS 指数导入与月度赋形

## 数据层

### 迁移 006 + 模型 `app/models/price_index_snapshot.py`

```python
class PriceIndexSnapshot(Base):
    region_type: str      # 'city'
    region_id: int
    year_month: str       # 'YYYY-MM'
    dwelling_type: str    # 'new' | 'second'
    base_type: str        # 'mom'（本轮只导环比；表结构预留 yoy/fixed）
    index_value: float    # 上月=100
    source: str           # 'nbs_github_changao1'
    # UNIQUE(region_type, region_id, year_month, dwelling_type, base_type, source)
```

### 导入 `app/services/index_import.py`

1. httpx 下载 `raw.githubusercontent.com/changao1/.../merged_housing_data_eng.csv`
   （下载失败抛错给 job，不静默）。
2. 解析：每行 城市英文名 × 月份 × new_home_price_index / existing_home_price_index。
3. 城市对齐：静态 crosswalk `NBS_CITY_NAME_MAP`（70 项，EN→city.name 中文），
   放 `app/services/` 常量或独立数据文件；实施时先抽样 CSV 与 city 表实际值
   再定映射（58 导入时 city.name 的实际格式已知可查）。未匹配→跳过并计数。
4. 幂等 upsert（on_conflict_do_update by 唯一键）。
5. 返回 {imported, cities_matched, cities_skipped: [...], months_range}。

### 入口

`POST /admin/collect/import-annual` 的既有模式复制：
`POST /admin/collect/import-index` → job_runner 异步 job。
前端 DataManageView 仿年度导入按钮+统计条。

## ML 月度赋形（dataset.py）

### 读取

构建器新增内部步骤：对年度源覆盖的城市集合，一次性查
`price_index_snapshot`（dwelling_type='second', base_type='mom'）按城市分组，
得 `index_series: dict[region_id, dict[year_month, float]]`。
（二手房指数与挂牌均价口径最接近；新建留作后续对比。）

### 赋形算法 `_shape_with_index(anchors, index_chain)`

年度锚点 (m0,p0), (m1,p1)（相邻 12 月点，已校准）之间：

1. 链式还原：`chain[m] = ∏(index[k]/100 for k in (m0, m]]`，得指数隐含的
   相对轨迹 `p0 * chain[m]`。
2. 锚点对齐：指数隐含的 m1 值 `p0*chain[m1]` 与真实锚点 p1 有偏差，
   对每个中间月乘几何渐变修正
   `(p1 / (p0*chain[m1])) ** (t/T)`（t=距 m0 月数，T=段长 12）——
   锚点值精确保持，段内形状来自指数、水平漂移被均匀吸收。
3. 段内任一月指数缺失 → 该段整体回退线性插值（不混拼）。
4. 序列首锚点前/末锚点后的悬空段维持现状（不外推）。

### 元数据与一致性

- DatasetMeta 增 `shaping: {"nbs_index": n_cities, "linear": m_cities}`。
- 训练与预测同走 `build_multi_source_series` → 预测侧自动同形；
  取数在构建器内完成（新增 session 依赖或由调用方传入 index rows——
  取后者：`build_multi_source_series(rows_by_source, index_rows=None, ...)`，
  predictions/train 两个调用点由 `select_index_snapshots` 服务函数供数，
  保持 dataset.py 纯函数无 DB 依赖的现状）。
- 权重不变（仍 0.3）：形状真实了，但水平仍是年度挂牌校准值，谨慎为先。

## 权衡

- 只用二手环比、只用 changao1：一个口径先跑通端到端；多口径（hugohe3
  定基/同比）等审计任务证明价值后再扩。
- 几何渐变对齐而非比例平摊：环比链的误差随月累积，几何渐变把闭合误差
  均匀分布，避免段尾跳变。
- crosswalk 用静态映射而非模糊匹配：70 项一次写死，可审计、无误配风险。

## 回滚

- 迁移 006 可 down；赋形失败/回退线性由段级 fallback 保证；
  `index_rows=None` 时行为与现状完全一致。
