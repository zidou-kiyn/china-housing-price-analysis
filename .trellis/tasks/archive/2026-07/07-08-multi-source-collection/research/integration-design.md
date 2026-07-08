# 多源采集 + 前端数据源切换 —— 文件级集成改造方案

> 只读调研产出。以下为逐文件、逐函数的改动清单、推荐方案与理由、迁移需求、回滚点。
> 现状已核对：唯一源 `creprice`；`admin_collect.py` 硬编码 `SOURCE_NAME="creprice"`；
> `PipelineRunner.run` 硬编码调用 `fetch_districts` / `fetch_price_distribution` / `source.BASE_URL`；
> `price_snapshot` 无 source 维度（唯一约束 = region_type+region_id+year_month）。

---

## 0. 现状关键事实（影响面清单）

- **源注册链**：`app.collector.__init__` → `app.collector.sources.__init__` → 导入 `creprice.py` → 末行 `SourceRegistry.register(...)`。
  只要 `admin_collect.py` `from app.collector.base import SourceRegistry` 触发 `app.collector` 包初始化，注册即完成。`SourceRegistry.names()` 在启动时已可用。
- **`source_name` 定义不一致**：`base.py` 声明为 `@property @abstractmethod`，但 `creprice.py` 用**类属性** `source_name = "creprice"` 覆盖（`register()` 时按类属性读取）。capability 也应设计为**类级属性**，避免为读能力而实例化（实例化会 new 一个 `CrawlerHttpClient`）。
- **`PriceSnapshot` 的读消费点（加 source 列的影响面）**——全部按 `region_type + region_id` 过滤，无 source 概念：
  - `api/v1/prices.py`:45（趋势）、:128-140（区县概览取 latest_month）
  - `api/v1/analytics.py`:69（rank/compare 批量取快照）
  - `api/v1/predictions.py`:43（训练取数）
  - `api/v1/admin_collect.py`:64-72（覆盖状态 latest_month）、:125（all_missing 判定）
  - `pipeline/loaders.py`:92（写入 upsert）
  → 只要唯一约束里**加入 source**，以上 6 处读点都会跨源重复计数，必须逐点加 source 过滤。这是选型 3 的核心权衡。
- **`crawl_job` 已有 `source` 列**（`models/crawl_job.py`:13，`create_crawl_job(session, source, city_code)` 已写入）。→ 溯源到 job 级几乎零成本。
- **前端参考**：`DataManageView.vue` 的「采集代理」卡片（`proxy-card`）+ `admin.ts` 的 `fetchProxySetting/saveProxySetting/testProxy` + `types/index.ts` 的 `ProxySetting` —— 数据源卡片照此风格复制。

---

## 1. 数据源选择泛化（去掉硬编码 `SOURCE_NAME`）

### 推荐：方案 (c) 两者结合 —— KV 存"当前默认源" + 采集请求可选 `source` 覆盖

理由：
- **KV 默认源**沿用 proxy-settings 已验证的 `app_setting` KV 模式，`refresh_cities` 与后台采集任务无需把 source 参数层层透传即可工作；前端"切换数据源"即改这一个 KV（与需求"数据源切换"语义完全一致）。
- **请求级 `source` 覆盖**给显式控制与可测试性（单次采集某源而不改全局默认），也为将来 per-job 选源留口子。
- 解析优先级：`payload.source`（显式） > KV 当前源 > 常量兜底 `"creprice"`。

### 改动点

**`backend/app/services/app_settings.py`** —— 复用现有 KV，新增源相关 helper：
```python
COLLECT_SOURCE_KEY = "collect_source"
DEFAULT_SOURCE = "creprice"

async def get_collect_source(session: AsyncSession) -> str:
    """读取当前默认采集源；未配置回退 DEFAULT_SOURCE。"""
    value = await get_setting(session, COLLECT_SOURCE_KEY)
    return (value or {}).get("source") or DEFAULT_SOURCE

async def set_collect_source(session: AsyncSession, source: str) -> None:
    await set_setting(session, COLLECT_SOURCE_KEY, {"source": source})
```
（无需 sync 版：采集编排全在 async 上下文，源在 API 层解析后透传给 runner；对比 proxy 之所以要 sync，是因为 `CrawlerHttpClient` 在工作线程里同步构造。）

**`backend/app/schemas/admin_job.py`** —— `CollectRequest` 增一字段：
```python
class CollectRequest(BaseModel):
    city_codes: list[str] = Field(default_factory=list)
    all: bool = False
    all_missing: bool = False
    source: str | None = None   # None = 用当前默认源（KV）
```

**`backend/app/api/v1/admin_collect.py`** —— 删掉模块常量 `SOURCE_NAME = "creprice"`，改为运行时解析：
- 顶部新增 `from app.services.app_settings import get_collect_source`，并新增一个校验 helper：
  ```python
  def _resolve_source(name: str) -> str:
      if name not in SourceRegistry.names():
          raise ApiError(422, f"未知数据源: {name}", "VALIDATION_ERROR")
      return name
  ```
- `refresh_cities`（:41）：`source_name = _resolve_source(await get_collect_source(db))`；`SourceRegistry.get(source_name)`。（可选：给 `refresh_cities` 加 `source: str | None = Query(None)` 覆盖）
- `submit_collect`（:170）：
  ```python
  source_name = _resolve_source(payload.source or await get_collect_source(db))
  job = await job_runner.submit(
      "collect",
      {"city_codes": city_codes, "source": source_name},   # 落进 payload，便于历史追溯/前端展示
      lambda job_id: _run_collect(job_id, city_codes, source_name),
      progress_total=len(city_codes),
  )
  ```
- `_run_collect`（:147）签名加 `source_name: str`，把 `runner.run(SOURCE_NAME, code)` 改为 `runner.run(source_name, code)`。

> 结果：`admin_collect.py` 内再无任何写死的源名；源要么来自请求、要么来自 KV，非法源在 API 层 422。

---

## 2. 异构源能力声明（capability 机制）

### 推荐：`BaseSource` 类级 `capabilities: frozenset[str]` + `supports()`；runner 按能力跳步

不同源能力不同（无区县 / 无分布 / 政府源是指数非 ¥/㎡）。让 `PipelineRunner.run` 依据能力跳过，而非硬调用。

### 改动点

**`backend/app/collector/base.py`**：
```python
# 采集数据类型常量（能力标识）
class DataType:
    CITIES = "cities"
    DISTRICTS = "districts"
    PRICE_TIMELINE = "price_timeline"
    PRICE_DISTRIBUTION = "price_distribution"

class BaseSource(ABC):
    # 类级：默认只保证城市 + 城市级时序（最小可用源）
    capabilities: frozenset[str] = frozenset(
        {DataType.CITIES, DataType.PRICE_TIMELINE}
    )
    # 元数据：均价语义（¥/㎡ vs 指数）——供前端/清洗区分，MVP 仅声明不改存储
    price_unit: str = "cny_per_sqm"   # 政府指数源可设 "index"
    base_url: str = ""                # 取代 runner 里硬取的 source.BASE_URL

    @classmethod
    def supports(cls, data_type: str) -> bool:
        return data_type in cls.capabilities

    # 可选能力：默认 stub，声明了 DISTRICTS/PRICE_DISTRIBUTION 的源才覆盖
    def fetch_districts(self, city_code: str | None = None) -> list["DistrictInfo"]:
        raise NotImplementedError

    def fetch_price_distribution(self, city_code: str, district_code: str = "allsq1") -> "RawRecord":
        raise NotImplementedError
```
- 给 `SourceRegistry` 加 `get_class(name)` classmethod（暴露类以便 `GET /sources` 读 capabilities/price_unit 而不实例化）：
  ```python
  @classmethod
  def get_class(cls, name: str) -> type[BaseSource]:
      if name not in cls._registry:
          raise KeyError(f"未注册的数据源: {name}")
      return cls._registry[name]
  ```

**`backend/app/collector/sources/creprice.py`**：声明满能力（保证零回归）：
```python
class CrepriceSource(BaseSource):
    source_name = "creprice"
    base_url = "https://creprice.cn"       # 新增小写，供 runner 用
    BASE_URL = "https://creprice.cn"       # 保留旧大写，兼容现有引用
    capabilities = frozenset({
        DataType.CITIES, DataType.DISTRICTS,
        DataType.PRICE_TIMELINE, DataType.PRICE_DISTRIBUTION,
    })
```

**`backend/app/pipeline/runner.py`** `run()`（:38-102）—— 按能力包裹每个可选阶段：
- 区县维度（`_load_dimensions` 内的 `fetch_districts`，及后续区县时序/区县分布循环 :63-87）：仅当 `source.supports(DataType.DISTRICTS)`。不支持时返回空 `dist_list`，跳过两个 for 循环。
- 城市分布 :73-77 + 区县分布 :79-87：仅当 `source.supports(DataType.PRICE_DISTRIBUTION)`。
- 城市时序 :57-61 始终执行（最小能力）。
- 具体改法（示意）：
  ```python
  supports_dist = source.supports(DataType.DISTRICTS)
  supports_distribution = source.supports(DataType.PRICE_DISTRIBUTION)
  city_map, dist_map, dist_list = await self._load_dimensions(
      session, source, city_code, job.id, with_districts=supports_dist)
  ...
  if supports_dist:
      for dist in dist_list: ...   # 区县时序
  if supports_distribution:
      n = await self._load_city_distribution(...)
      if supports_dist:
          for dist in dist_list: ...   # 区县分布
  ```
- `_load_dimensions`（:104-137）：
  - 加参数 `with_districts: bool`；`with_districts` 为 False 时不调用 `source.fetch_districts`，`dist_list=[]`, `dist_map={}`。
  - 把两处硬编码 `source.BASE_URL`（:120、:132）改为 `getattr(source, "base_url", "") or source.source_name`（避免无 `BASE_URL` 的源 AttributeError）。

> 结果：runner 不再假设任意 fetch 方法存在；新源只需声明 `capabilities` 与实现对应 fetch，即可安全接入。

---

## 3. 多源共存与数据模型

### 推荐：MVP 走 (b) 单值 latest-wins + 溯源到 job；给 `price_snapshot` 加**可空 `source` 注记列（不进唯一约束）**作为廉价中间态。完整多源并存对比 (a) 记录为后续可选项。

理由：
- PRD 目标是"多源混合与**数据源切换**"，是"换用哪个源产出规范数据"，不是"同城同月多源并排对比"。切换语义下**单值表 + 当前源**即满足 MVP。
- 若把 `source` 加进**唯一约束**（方案 a），第 0 节列出的 **6 个读点全部跨源重复**，需逐点加 `source` 过滤 + 前端每个读视图都要带源选择；alembic 要改唯一约束（先删旧约束再建新约束，需回填历史行 source）；blast radius 很大，不适合 MVP。
- 折中：**加 `source String nullable` 列但唯一约束不变**。upsert 时写入"最后写入者"的 source，读点**完全不用改**（不进过滤），却获得：① 覆盖状态可显示"当前数据来自哪个源"徽标；② 为将来升级到 (a) 预留列（迁移时只需改约束+回填即可）。

### 方案对比表

| 维度 | (b) latest-wins + 注记列（推荐 MVP） | (a) source 进唯一约束（并存对比，后续） |
|---|---|---|
| alembic | 加 1 个 nullable 列，可空、无回填强制、可逆 | 加列 + 回填历史 source + drop/create 唯一约束 + 同步 `price_distribution` 约束 |
| loaders.py | `upsert_price_snapshots` 增 `source` 入参写入列；`on_conflict` 约束名不变 | conflict target 改含 source；`upsert_price_distributions` 同改 |
| 读 API（prices/analytics/predictions/admin_collect） | **零改动** | 6 处全部加 `.where(source == 当前源)`，否则重复行 |
| 前端 | 覆盖表可选加"来源"列（读注记列） | 每个读视图都要传 source；对比视图需并排渲染多源 |
| 风险 | 低（现有 creprice 全量数据/流程不变） | 高（读路径全线回归风险） |

### 改动点（推荐方案 b）

**`backend/app/models/price_snapshot.py`**：新增
```python
source: Mapped[str | None] = mapped_column(String(20))   # 该行最后写入的数据源，唯一约束不含它
```
（`price_distribution.py` 可同样加，或 MVP 先只加 snapshot。）

**`backend/alembic/versions/004_price_snapshot_source.py`**（新迁移，参照 003 风格）：
```python
revision = "004"; down_revision = "003"
def upgrade():
    op.add_column("price_snapshot", sa.Column("source", sa.String(20), nullable=True))
    # 可选：回填历史行为 'creprice'（当前唯一源）
    op.execute("UPDATE price_snapshot SET source = 'creprice' WHERE source IS NULL")
def downgrade():
    op.drop_column("price_snapshot", "source")
```

**`backend/app/pipeline/loaders.py`** `upsert_price_snapshots`（:71）：签名加 `source: str`，rows 里加 `"source": source`，`on_conflict_do_update` 的 `set_` 里加 `"source": stmt.excluded.source`（约束名 `uq_price_snapshot_region_month` 不变）。

**`backend/app/pipeline/runner.py`**：`_load_city_timeline` / `_load_district_timeline` 透传 `source.source_name` 给 `upsert_price_snapshots`。

> 注意"政府源是指数非 ¥/㎡"：MVP 用 `BaseSource.price_unit` 元数据声明，不混入同一 `supply_price` 列做跨源可比。若真要接指数源并存，属于 (a) 的范畴，MVP 不做——先在设计里标记，避免指数值污染 creprice 的 ¥/㎡ 均价。

---

## 4. 前端数据源切换

在 `DataManageView.vue` 顶部（proxy-card 上方或下方）加「数据源」卡片，复制 proxy-card 风格。

### 新 API

- `GET /admin/collect/sources` → 列出可用源 + 能力 + 当前默认源。
- `PUT /admin/collect/source` → 设置当前默认源（写 KV）。
  （放在 `admin_collect.py` router `/admin/collect` 下，语义比 `/admin/settings` 更贴切；也可放 `admin_settings.py`，二选一，推荐前者。）

**`backend/app/schemas/admin_job.py`**（或新建 `schemas/source.py`）新增：
```python
class CollectSourceOut(BaseModel):
    name: str
    capabilities: list[str]
    price_unit: str

class CollectSourcesResponse(BaseModel):
    current: str
    items: list[CollectSourceOut]

class CollectSourceUpdate(BaseModel):
    source: str
```

**`backend/app/api/v1/admin_collect.py`** 新增两端点：
```python
@router.get("/sources", response_model=CollectSourcesResponse)
async def list_sources(db=Depends(get_session), _admin=Depends(require_admin)):
    current = await get_collect_source(db)
    items = []
    for name in SourceRegistry.names():
        cls = SourceRegistry.get_class(name)
        items.append(CollectSourceOut(
            name=name, capabilities=sorted(cls.capabilities), price_unit=cls.price_unit))
    return CollectSourcesResponse(current=current, items=items)

@router.put("/source", response_model=CollectSourcesResponse)
async def set_source(payload: CollectSourceUpdate, db=..., _admin=...):
    _resolve_source(payload.source)          # 未注册 → 422
    await set_collect_source(db, payload.source)
    return await list_sources(db, _admin)    # 或重组返回
```

**`frontend/src/types/index.ts`** 新增：
```ts
export interface CollectSource {
  name: string
  capabilities: string[]
  price_unit: string
}
export interface CollectSourcesResponse {
  current: string
  items: CollectSource[]
}
```

**`frontend/src/api/admin.ts`** 新增（放「采集代理设置」段旁）：
```ts
export function fetchCollectSources(): Promise<CollectSourcesResponse> {
  return api.get('/admin/collect/sources')
}
export function saveCollectSource(source: string): Promise<CollectSourcesResponse> {
  return api.put('/admin/collect/source', { source })
}
```

**`frontend/src/views/admin/DataManageView.vue`**：
- `<script setup>`：import 上述两个 api + `CollectSource` 类型；新增 `const sources = ref<CollectSource[]>([])` 与 `const currentSource = ref('')`；`loadSources()`（onMounted 里并入 `Promise.all`）；`onChangeSource()` 调 `saveCollectSource` 后 `ElMessage.success`。
- 模板：在 proxy-card 旁加 `source-card`，用 `el-select`（`v-model="currentSource"` `@change="onChangeSource"`）列出 `sources`；每项可用 `el-tag` 展示 capabilities/price_unit。
- （可选增强）批量采集区加一个"本次采集使用源"下拉，映射到 `submitCollect({..., source})` 覆盖默认源；MVP 可省，仅用卡片切默认源。

样式：复制 `.proxy-card` / `.proxy-row` / `.proxy-label` 命名为 `.source-*`，保持视觉一致。

---

## 5. 兼容与回滚（保证 creprice 现有全量数据/流程不回归）

**兼容保证**：
1. `CrepriceSource` 声明**满能力**（4 项）→ runner 走与今天完全一致的四阶段流程，无跳步。
2. `payload.source` 默认 `None`、KV 未配置时 `get_collect_source` 回退 `DEFAULT_SOURCE="creprice"` → 老前端/老调用不带 source 也照旧跑 creprice。
3. 迁移 004 仅**加可空列**，不动唯一约束、不改任何读查询 → 现有趋势/排名/预测/覆盖状态 API 输出不变。历史行回填 `source='creprice'` 是幂等 UPDATE。
4. 保留 `CrepriceSource.BASE_URL` 大写别名，runner 改用 `getattr(source, "base_url", ...)`，即使漏改也不 AttributeError。
5. 前端新卡片是纯增量组件，不改动现有覆盖表/任务区逻辑。

**回滚点（从低风险到高风险，可独立回退）**：
- R1 前端：撤掉 `source-card` + `admin.ts`/`types` 新增 → 回到今天 UI，后端不受影响。
- R2 API：`GET/PUT /sources`、`CollectRequest.source`、`_resolve_source` 可整体移除；把源解析改回常量 `"creprice"`。
- R3 能力机制：runner 的 `supports()` 跳步若出问题，creprice 满能力下与原逻辑等价；可临时把 `run()` 恢复为无条件调用。
- R4 迁移：`alembic downgrade 003` 即 `drop_column source`，无数据损失（该列仅注记）。
- R5 KV：`collect_source` key 删除即回退默认源；不影响 `crawler_proxy`。

**建议落地顺序（小步提交，符合项目 commit-per-part 约定）**：
1. base.py capabilities/DataType/get_class + creprice 声明满能力（无行为变化）。
2. runner 按能力跳步 + 去 BASE_URL 硬编码。
3. app_settings 源 helper + CollectRequest.source + admin_collect 去 SOURCE_NAME。
4. 迁移 004 + loaders/runner 写 source 注记列。
5. `GET/PUT sources` 端点 + schema。
6. 前端数据源卡片。

---

## 附：关键文件索引（绝对路径）

- 抽象层：`/home/heixiaohu/桌面/Urban_Housing_Price_Analysis_System/backend/app/collector/base.py`
- 唯一源：`/home/heixiaohu/桌面/Urban_Housing_Price_Analysis_System/backend/app/collector/sources/creprice.py`
- 编排：`/home/heixiaohu/桌面/Urban_Housing_Price_Analysis_System/backend/app/pipeline/runner.py`
- 写库：`/home/heixiaohu/桌面/Urban_Housing_Price_Analysis_System/backend/app/pipeline/loaders.py`
- 采集 API：`/home/heixiaohu/桌面/Urban_Housing_Price_Analysis_System/backend/app/api/v1/admin_collect.py`
- 设置 API（proxy 参照）：`/home/heixiaohu/桌面/Urban_Housing_Price_Analysis_System/backend/app/api/v1/admin_settings.py`
- KV 服务：`/home/heixiaohu/桌面/Urban_Housing_Price_Analysis_System/backend/app/services/app_settings.py`
- schema：`/home/heixiaohu/桌面/Urban_Housing_Price_Analysis_System/backend/app/schemas/admin_job.py` / `.../schemas/settings.py`
- 模型：`.../models/price_snapshot.py`、`.../models/crawl_job.py`、`.../models/app_setting.py`
- 迁移目录：`/home/heixiaohu/桌面/Urban_Housing_Price_Analysis_System/backend/alembic/versions/`（003 为参照）
- 前端：`/home/heixiaohu/桌面/Urban_Housing_Price_Analysis_System/frontend/src/views/admin/DataManageView.vue`、`.../api/admin.ts`、`.../types/index.ts`
