# 技术设计 - 基础查询 API

## 模块边界

```
backend/app/
├── api/v1/
│   ├── router.py          # 主路由（挂载子路由）
│   ├── cities.py           # 城市/区县端点
│   └── prices.py           # 均价走势/分布/概览端点
├── schemas/
│   ├── city.py             # CityOut, DistrictOut
│   └── price.py            # TrendPoint, DistributionItem, DistrictOverviewItem
└── api/deps.py             # 已有：get_session, get_cache
```

## API 设计

### 城市与区县

| Method | Path | Response |
|--------|------|----------|
| GET | `/api/v1/cities` | `list[CityOut]` |
| GET | `/api/v1/cities/{city_code}/districts` | `list[DistrictOut]` |

### 价格数据

| Method | Path | Params | Response |
|--------|------|--------|----------|
| GET | `/api/v1/prices/trend` | `region_type`, `region_id`, `months?` | `list[TrendPoint]` |
| GET | `/api/v1/prices/distribution` | `region_type`, `region_id`, `year_month?` | `list[DistributionItem]` |
| GET | `/api/v1/prices/overview` | `city_code` | `list[DistrictOverviewItem]` |

## 缓存策略

| 端点 | Key 模式 | TTL |
|------|----------|-----|
| cities | `api:cities` | 3600s |
| districts | `api:districts:{city_code}` | 3600s |
| trend | `api:trend:{region_type}:{region_id}` | 1800s |
| distribution | `api:dist:{region_type}:{region_id}:{year_month}` | 1800s |
| overview | `api:overview:{city_code}` | 1800s |

PipelineRunner 入库完成后应清除匹配 `api:*:{city_code}*` 的 key（与 runner.py 的 `_invalidate_cache` 对齐）。

## 查询逻辑

### overview 端点

```sql
SELECT d.id, d.name, d.code, ps.supply_price, ps.attention_price, ps.value_price
FROM district d
JOIN city c ON d.city_id = c.id
LEFT JOIN price_snapshot ps ON ps.region_type = 'district' AND ps.region_id = d.id
  AND ps.year_month = (SELECT MAX(year_month) FROM price_snapshot WHERE region_type = 'district' AND region_id = d.id)
WHERE c.code = :city_code
```

## 错误处理

- 未找到城市：404 `{"detail": "城市不存在"}`
- 无数据：返回空数组 `[]`（不是 404）
