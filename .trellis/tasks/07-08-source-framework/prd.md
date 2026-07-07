# 多源框架泛化与数据源切换（child A）

> 父任务：`07-08-multi-source-collection`。本任务是其余新源（国家统计局 / Kaggle / 中介站）接入的**地基**，须先落地。

## Goal

让采集框架不再假设"只有 creprice、且必有区县+分布"：解耦硬编码 `SOURCE_NAME`，引入源**能力声明**并让编排层按能力自适应跳步，新增"可用源列表 / 当前源"API 与前端**数据源切换**卡片。creprice 现有全量数据与流程零回归。

## Requirements

1. **去硬编码源名**：`admin_collect.py` 不再写死 `SOURCE_NAME="creprice"`。当前源来源优先级：采集请求 `payload.source`（显式）> `app_setting` KV `collect_source` > 常量兜底 `creprice`。非法源在 API 层返回 422。
2. **能力声明**：`BaseSource` 增类级 `capabilities: frozenset[str]`（`cities/districts/price_timeline/price_distribution`）、`price_unit` 元数据、`supports()`。creprice 声明满能力。
3. **按能力编排**：`PipelineRunner.run` 依据 `supports()` 跳过不支持的区县 / 分布阶段，不再无条件调用 `fetch_districts` / `fetch_price_distribution`；去掉对 `source.BASE_URL` 的硬取（改 `getattr`）。
4. **数据源切换 API**：
   - `GET /admin/collect/sources`：列出已注册源 + 能力 + `price_unit` + 当前默认源。
   - `PUT /admin/collect/source`：设置当前默认源（写 KV）。
5. **溯源注记列**：`price_snapshot` 加可空 `source` 列（**不进唯一约束**），upsert 时写"最后写入源"。读点零改动。alembic 迁移 004（可空列 + 幂等回填 `creprice`，downgrade 可逆）。
6. **前端切换卡片**：`DataManageView.vue` 加「数据源」卡片（复用 proxy-card 风格），`el-select` 切换当前源并展示各源能力标签。

## 非目标（MVP 明确不做）

- 同城同月**多源并排对比**（需 source 进唯一约束 + 6 处读点改造，blast radius 大，列为后续可选项 (a)）。
- 指数类数据（政府源 `price_unit="index"`）**混入** creprice 的 ¥/㎡ 列做跨源可比——本任务只声明 `price_unit`，不做混算。

## Acceptance Criteria

- [ ] `admin_collect.py` 无写死源名；不带 source 的老调用仍走 creprice（回退验证）。
- [ ] 注册一个"仅城市+时序"的假源（或用 stub 验证）时，`PipelineRunner.run` 能跳过区县/分布不报错；creprice 满能力时四阶段流程与改造前等价。
- [ ] `GET /admin/collect/sources` 返回 creprice（满能力）+ 当前源；`PUT /admin/collect/source` 切换后再次 GET 生效；切非法源 422。
- [ ] 迁移 004 升级后 `price_snapshot.source` 存在、历史行回填 `creprice`；`alembic downgrade 003` 可逆。
- [ ] 前端「数据源」卡片可读取并切换当前源，能力标签正确展示。
- [ ] 后端既有测试 + 新增能力/源解析单测通过；creprice 抽查采集一城，snapshot 落库且 `source='creprice'`。
