# M1-5 基础查询 API

## Goal

提供城市/区县元数据查询与均价走势、价格分布的 RESTful API，支撑前端搜索与图表渲染。

## Requirements

- **城市列表** `GET /api/v1/cities`
  - 返回所有城市（id, name, code）
  - 支持 Redis 缓存（TTL 1h）

- **区县列表** `GET /api/v1/cities/{city_code}/districts`
  - 返回指定城市下的区县（id, name, code）
  - 支持 Redis 缓存（TTL 1h）

- **均价走势** `GET /api/v1/prices/trend?region_type=city&region_id=1`
  - 返回指定区域的按月均价时序（year_month, supply_price, attention_price, value_price, sample_count）
  - 支持可选参数 `months` 限制返回月数（默认全部）
  - 支持 Redis 缓存（TTL 30min）

- **价格分布** `GET /api/v1/prices/distribution?region_type=city&region_id=1`
  - 返回指定区域最新月份的价格区间分布
  - 支持可选参数 `year_month` 指定月份（默认最新）
  - 支持 Redis 缓存（TTL 30min）

- **区县均价概览** `GET /api/v1/prices/overview?city_code=qz`
  - 返回某城市下所有区县的最新月份均价（用于柱状图）
  - 支持 Redis 缓存（TTL 30min）

## Constraints

- 所有接口使用 Pydantic v2 schema 做响应序列化
- 缓存 key 模式与 PipelineRunner 的缓存失效逻辑对齐
- 不需要认证（M1 阶段公开读取）

## Acceptance Criteria

- [x] `GET /api/v1/cities` 返回包含泉州的城市列表
- [x] `GET /api/v1/cities/qz/districts` 返回泉州 3 个区县
- [x] `GET /api/v1/prices/trend?region_type=city&region_id=403` 返回 13 个月数据（≥12）
- [x] `GET /api/v1/prices/distribution?region_type=city&region_id=403` 返回 21 条分布数据
- [x] `GET /api/v1/prices/overview?city_code=qz` 返回 3 个区县均价
- [x] 重复请求命中 Redis 缓存（test_cache_hit 验证）
- [x] 接口测试覆盖正常和异常路径（18 tests）

## Dependencies

- M1-4 pipeline-clean-load（数据库中已有泉州数据）✅
