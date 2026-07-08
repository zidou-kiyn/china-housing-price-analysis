# 国家统计局指数源适配器（child B）

> 父任务：`07-08-multi-source-collection`。依赖 child A。**live 抓取受阻于 IP 地理围栏**（境外 403），本环境仅能离线验证解析逻辑。

## 背景

国家统计局是最权威的房价数据源，但 `data.stats.gov.cn/easyquery.htm` 被 WAF 按 IP 地理围栏硬拦（`reason:UrlACL`），境外 IP 一律 403，与 Header/Cookie 无关；所给美国代理对该站 TLS 直接 RST。**接入唯一前置是中国大陆出口 IP**。数据是 70 城房价**指数**（100 基准 float，非 ¥/㎡），月度、无区县。

## Goal

实现 `GovStatsSource` 适配器（easyquery 客户端 + 指数响应解析），**离线单测**保障解析正确；注册进框架使其在数据源切换 UI 可见（`price_unit=index`）；给 runner 加守卫，指数源被 ¥/㎡ 时序管线拒绝（清晰报错），避免污染。一旦提供大陆 IP 即可 live 抓取。

## Requirements

1. `easyquery()` 客户端：与官方前端一致的 headers/params（POST form、k1 时间戳、trust_env=False、显式 proxy），403/UrlACL → 抛 `GovStatsBlockedError`（提示需大陆 IP）。
2. `parse_index_response()`：datanodes + wds + wdnodes → 归一化记录（region_code/name、zb_code/name、year_month、index_value），`hasdata=false` 跳过，`202405`→`2024-05`。
3. `GovStatsSource`：`capabilities={PRICE_INDEX}`、`price_unit=index`、注册；`fetch_price_index(reg,zb,sj)`；`fetch_price_timeline` 抛 NotImplementedError（指数源）；默认读管理端代理（应配国内代理）。
4. `DataType.PRICE_INDEX` 常量；`PipelineRunner.run` 守卫：不支持 PRICE_TIMELINE 的源直接 ValueError。
5. 离线单测：解析归一化/跳过缺失/空响应、timeline 不支持、403→GovStatsBlockedError。

## 非目标（后续，需大陆 IP）

- `price_index_snapshot` 新表 + 指数入库管线 + 指数专用读 API + 前端指数展示。
- `region_map` 码表（NBS 6 位 GB 码 ↔ creprice 城市码对齐）。
- 全国/分省 销售额÷销售面积 推算绝对均价。
- live 端到端抓取验证（受 IP 阻塞）。

## Acceptance Criteria

- [x] `govstats` 注册，`GET /admin/collect/sources` 显示 price_unit=index、能力 price_index；前端切换下拉可见。
- [x] `PipelineRunner.run('govstats', ...)` 被守卫拒绝并给出可操作报错（不写坏数据）。
- [x] 离线解析单测通过（含 hasdata 跳过、YYYYMM 归一化、403 阻塞错误）。
- [x] creprice/kaggle ¥/㎡ 管线不受守卫影响（回归通过）。
- [ ] （阻塞）提供中国大陆 IP 后 live 抓取 70 城指数——留待用户提供代理。
