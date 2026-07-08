# 技术设计——源隔离展示（全局数据源切换器）

## 边界与总原则

读取层从"多源同月合并取一行"改为"单源直读"。合并只发生在**读取层**，删掉它即实现
硬隔离；存储层（各源独立行）与 ML 层（child 2 管）不动。前端引入唯一的全局
`source` 状态，串到所有价格/分析请求。

价格快照源（`price_snapshot.source`）= `source_policy.SOURCE_PRIORITY` 的键：
`creprice / kaggle_lianjia / listing_annual_58 / listing_annual_anjuke`。NBS 指数
**不是** price_snapshot 源，走独立的 `price_index_snapshot` 路径，前端单独处理。

## 后端

### 契约：`source` 查询参数（R1）
- 适用端点：`/prices/trend`、`/prices/distribution`、`/prices/overview`、
  `/analytics/rank`、`/analytics/compare`、`/analytics/map/heat`。
- 取值域 = 已登记 price_snapshot 源；缺省 `creprice`；非法值 → **422**。
- 统一实现：`app/core/source_policy.py` 暴露 `REGISTERED_SOURCES: tuple[str,...]`
  （= SOURCE_PRIORITY 键，按优先级排序）+ `DEFAULT_SOURCE = "creprice"`；
  `app/api/deps.py` 加依赖 `source_param(source: str = Query(DEFAULT_SOURCE)) -> str`，
  非登记源抛 `HTTPException(422, ...)`。各端点 `source: str = Depends(source_param)`。

### 删合并路径（R2）
- 删除 `price_select.select_merged_snapshots` 与 `source_policy.priority_case`
  （priority_case 仅被 merged 使用，grep 已确认）。SOURCE_PRIORITY/source_priority
  保留（trend/series 排序、ML、审计仍用）。
- 新增 `price_select.select_snapshots_for_source(session, source, region_type, region_ids)
  -> list[PriceSnapshot]`：`WHERE source == :source`，区域/月份升序，不做任何合并。
- 消费方改造：
  - `prices.price_trend`（原 :47）→ `select_snapshots_for_source(db, source, rt, [rid])`。
  - `analytics._load_snapshots`（原 :73）→ 加 `source` 形参，改走单源查询。
- `/prices/trend/series`（多源分线）**保留不动**——它是"对比展示"显式入口，非隐式混合。

### 单源口径（R4，后端天然满足）
读取层只回原始行、从不插值（插值仅在 ML 层）。故：
- creprice：月度行原样（现状不变）。
- 58 年度：年度行（year_month=YYYY-12）原样返回；rank 的 `_shift_month(-1)` 找不到
  相邻月 → mom_pct=None，`_shift_month(-12)` 命中上年 → yoy_pct 有值；year_month
  字段即带年份，前端标注。无任何月度换算。
- kaggle：仅北京有行，其余区域查询空 → []（前端空态）。
- distribution：`price_distribution` 表**无 source 列**，是 creprice 衍生产物；
  `source != creprice` 时直接返回 `[]`（其它源无分布数据，语义正确）。

### NBS 指数只读端点（R4d 所需，现无公开指数端点）
`prices.py` 加 `GET /prices/index/trend`（复用 `select_index_snapshots`，默认
second/mom）：`region_type, region_id` → `[{year_month, index_value}]`。新增 schema
`IndexTrendPoint`。仅供前端 NBS 源走势用；rank/compare/map 在 NBS 下前端不请求。

### 缓存键
所有涉及端点缓存键追加 `:{source}`，避免跨源串味（trend/dist/overview/rank/compare/map）。

## 前端

### 全局源状态（R3）
- 新建 `src/stores/source.ts`（Pinia setup 式，仿 auth.ts 手写持久化）：
  `current = ref(localStorage.getItem('data_source') || 'creprice')`，`setSource` 时
  `localStorage.setItem`。导出 `SOURCE_OPTIONS`：
  `creprice=月度实采 / listing_annual_58=年度挂牌 / kaggle_lianjia=历史成交 /
  nbs_index=官方指数`。
- `nbs_index` 是前端合成值（非后端 price_snapshot 源）；`isIndexSource = current==='nbs_index'`。
- `AppHeader.vue` 在 `.nav-menu` 与 `.user-area` 间插 `el-select`（仿 DataManageView
  的源切换器），绑 store.current。

### API 串参
`src/api/price.ts` / `analytics.ts` 的 trend/distribution/overview/rank/compare/mapHeat
函数加可选 `source` 形参 → 映射为 `source` query。新增 `fetchIndexTrend`（GET
`/prices/index/trend`）。predict 不加 source（predict 仅 creprice）。

### 各视图按源重拉（R3/R4/R6）
- Rank/Compare 已有 `watch` → watch 列表加 `sourceStore.current`。
- Home/Map/Dashboard 无 watch → 加 `watch(() => sourceStore.current, reload)`。
- 请求统一带 `sourceStore.current`（非 index 源）。
- index 源（nbs）：走势视图调 `fetchIndexTrend` 渲染指数曲线（单位=指数、基准 100，
  复用/扩展 TrendLine 或简单 line）；rank/compare/map/distribution/overview 显示
  "指数源不适用"提示，不发 ¥/㎡ 请求。
- 非 index 源下某区域无数据 → el-empty 显式空态（禁止静默回退，本任务核心）。

### 预测入口限定（R5）
各视图中跳转 PredictView 的入口（"查看预测"等，grep `predict`/`/predict/` 定位）
仅在 `current === 'creprice'` 时显示/可用；否则隐藏或禁用并提示"预测仅基于 creprice
实采数据"。

## 兼容与回滚
- 删 merged 走 git 历史可回（R2 已认可）。
- source_policy 优先级定义保留（仅剩切换器排序 + trend/series 分线排序用途）。
- 前端源切换器是叠加式改造，回滚 = 移除 store + 各视图 watch，不影响存量数据。

## 测试策略
- 后端：`test_prices.py` / `test_analytics.py` 加 source 分支——默认 creprice 单源、
  显式 `source=listing_annual_58` 取年度行、非法 source→422；改写原
  `test_trend_merges_multi_source_by_priority`（合并语义已废）为单源断言。
  `test_price_select.py` 删 merged 相关用例，保留 select_source_snapshots/index 用例，
  加 select_snapshots_for_source 用例。新增 `/prices/index/trend` 冒烟。
- 前端：`npm run build`（vue-tsc + vite）通过即门禁。
