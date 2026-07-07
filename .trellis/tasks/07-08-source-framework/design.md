# Design — 多源框架泛化与数据源切换（child A）

> 详版调研见 `../07-08-multi-source-collection/research/integration-design.md`。本文记录采纳的决策与契约。

## 关键现状（影响面）

- 源注册链：`import app.collector.base` 会触发 `app.collector` 包 `__init__` → 导入 `sources/creprice.py` 末行 `SourceRegistry.register(...)`，故启动即注册完成。
- `source_name` 在 `base.py` 是 `@property @abstractmethod`，但 creprice 用**类属性**覆盖 → capability/price_unit 也用**类级属性**，`GET /sources` 免实例化即可读（实例化会 new 一个 `CrawlerHttpClient`）。
- `crawl_job.source` 列**已存在**，`create_crawl_job(session, source, city_code)` 已写入 → job 级溯源零成本。
- `PriceSnapshot` 读点（prices/analytics/predictions/admin_collect/loaders 共 6 处）全部按 `region_type+region_id` 过滤、无 source 概念。

## 决策

### D1. 源选择：KV 默认源 + 请求级覆盖（方案 c）
解析优先级 `payload.source > KV(collect_source) > "creprice"`。KV 复用 proxy 已验证的 `app_setting` 模式，用 **async** helper（采集编排在 async 上下文解析后透传 runner；不需 proxy 那种 sync 版）。

### D2. 能力声明：类级 `capabilities: frozenset[str]` + `supports()`
`DataType` 常量：`CITIES / DISTRICTS / PRICE_TIMELINE / PRICE_DISTRIBUTION`。`BaseSource` 默认最小能力 `{CITIES, PRICE_TIMELINE}`，`price_unit="cny_per_sqm"`，`base_url=""`。可选 fetch（`fetch_districts`/`fetch_price_distribution`）在 base 提供 `raise NotImplementedError` stub。`SourceRegistry.get_class(name)` 暴露类。creprice 声明满 4 能力 + `base_url`（保留 `BASE_URL` 大写别名兼容）。

### D3. 编排按能力跳步
`runner.run`：`supports_dist = source.supports(DataType.DISTRICTS)`、`supports_distribution = ...`。`_load_dimensions` 加 `with_districts` 参数；不支持时 `dist_list=[]`。区县时序/城市分布/区县分布分别用 `if supports_*` 包裹。`_load_dimensions` 内两处硬取 `source.BASE_URL` 改 `getattr(source, "base_url", "") or source.source_name`。

### D4. 溯源列：latest-wins + 可空 `source`（方案 b，不进唯一约束）
`price_snapshot` 加 `source: Mapped[str|None] = mapped_column(String(20))`。唯一约束 `uq_price_snapshot_region_month` **不变** → 6 处读点零改动。`upsert_price_snapshots` 加 `source` 入参，写入并进 `on_conflict_do_update.set_`。迁移 004：加可空列 + `UPDATE ... SET source='creprice' WHERE source IS NULL`，downgrade drop 列。
> 政府指数源以 `price_unit="index"` 声明，MVP **不**混入 `supply_price`；真正并存对比属后续方案 (a)。

### D5. 切换 API + 前端卡片
端点放 `admin_collect.py`（`/admin/collect` 前缀语义贴切）：`GET /sources`、`PUT /source`。schema 加 `CollectSourceOut{name,capabilities,price_unit}`、`CollectSourcesResponse{current,items}`、`CollectSourceUpdate{source}`。前端 `DataManageView.vue` 加 `source-card`（复制 `.proxy-card` 风格），`el-select` + 能力 `el-tag`；`admin.ts` 加 `fetchCollectSources/saveCollectSource`；`types/index.ts` 加对应接口。

## 契约（API）

```
GET  /api/v1/admin/collect/sources
 -> { current: "creprice", items: [ { name, capabilities: [...], price_unit } ] }
PUT  /api/v1/admin/collect/source   body { source: "creprice" }
 -> 同 GET 结构（切换后）；未注册源 -> 422 VALIDATION_ERROR
POST /api/v1/admin/collect          body 增可选 { source?: string }   # 覆盖本次采集源
```

## 兼容与回滚

- creprice 满能力 → runner 四阶段与今日等价；不带 source 的调用回退 creprice。
- 迁移 004 仅加可空列、不动约束、不改读查询 → 现有 API 输出不变；`downgrade 003` 无损。
- 回滚点 R1 前端卡片 / R2 API 端点+字段 / R3 能力跳步（满能力等价） / R4 迁移 / R5 KV key，均可独立回退。
- 保留 `CrepriceSource.BASE_URL` 别名；runner 用 `getattr` 兜底不 AttributeError。
