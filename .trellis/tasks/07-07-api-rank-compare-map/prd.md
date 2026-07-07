# M2-2 排行/对比/地图 API

## Goal

新增三个分析型查询端点（排行、对比、地图热力）并接入 Redis 缓存，为 M2-3 前端页面提供数据源。

## Requirements

### `GET /api/v1/rank` — 均价排行

- 查询参数：`region_type`（必填，`city|district`）、`city_code`（可选，region_type=district 时限定城市）、`sort_by`（默认 `supply_price`，可选 `supply_price|attention_price|value_price`）、`sort_order`（默认 `desc`）、`page`/`page_size`（默认 1/20）。
- 每项返回：`region_id`、`region_name`、`supply_price`、`attention_price`、`value_price`、`yoy_pct`（同比%）、`mom_pct`（环比%）、`year_month`（数据月份）。
- 同比/环比基于 price_snapshot 当月 vs 上月 vs 去年同月计算，缺基期则为 null；价格取各区域各自最新月份。
- 响应：`{total, page, page_size, items}` 分页包装。
- 排序按 sort_by 字段执行，null 价格排最后。

### `GET /api/v1/compare` — 多区域对比

- 查询参数：`region_type`（必填）、`region_ids`（必填，逗号分隔 2~5 个）、`months`（默认 12）、`price_type`（默认 `supply_price`）。
- 响应：`{price_type, regions: [{region_id, region_name, data: [{year_month, price}]}]}`。
- region_ids 数量 <2 或 >5 返回 422；不存在的 region_id 返回 404 `REGION_NOT_FOUND`。

### `GET /api/v1/map/heat` — 地图热力

- 查询参数：`city_code`（必填）、`region_type`（默认 `district`）。
- 响应：`{city_code, region_type, data: [{region_id, region_name, price}]}`，price 为该区域最新 supply_price。
- 前端 ECharts geo 按 region_name 与 GeoJSON name 匹配着色，故不返回经纬度（district 表无 lat/lng，docs/05 示例中的 lat/lng 字段按实际数据模型裁剪）。
- 城市不存在返回 404 `CITY_NOT_FOUND`。

### Redis 缓存

- 三端点均走 cache-aside（沿用 prices.py 现有模式），TTL 30 分钟。
- key 规范：`api:rank:{region_type}:{city_code}:{sort_by}:{sort_order}`（分页在缓存后切片）、`api:compare:{region_type}:{ids}:{price_type}`（months 在缓存后切片）、`api:mapheat:{city_code}:{region_type}`。

## 约束

- 本任务不做鉴权（compare/map 的 user 权限由 M2-4 统一收权）。
- 端点挂在新模块 `app/api/v1/analytics.py`（rank/compare/map 同属分析域），注册进 router。
- 错误响应格式与现有端点一致（HTTPException detail）。

## Acceptance Criteria

- [ ] `/rank?region_type=district&city_code=qz` 返回泉州 8 区县按 supply_price 降序，含 yoy/mom
- [ ] `/compare?region_type=district&region_ids=1,2` 返回两区县各 ≤12 个月走势
- [ ] `/compare` 传 1 个或 6 个 region_ids 返回 422
- [ ] `/map/heat?city_code=qz` 返回全部 8 区县名称+最新均价
- [ ] 二次请求命中 Redis 缓存（不再查库）
- [ ] pytest tests/api 全绿（新增用例覆盖上述场景）
