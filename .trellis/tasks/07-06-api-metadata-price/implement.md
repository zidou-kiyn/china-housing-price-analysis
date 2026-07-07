# 执行计划 - 基础查询 API

## 执行清单

- [x] 1. `app/schemas/city.py` — CityOut, DistrictOut Pydantic 模型
- [x] 2. `app/schemas/price.py` — TrendPoint, DistributionItem, DistrictOverviewItem
- [x] 3. `app/api/v1/cities.py` — 城市/区县路由 + Redis 缓存
- [x] 4. `app/api/v1/prices.py` — 均价走势/分布/概览路由 + Redis 缓存
- [x] 5. `app/api/v1/router.py` — 挂载 cities + prices 子路由
- [x] 6. `app/pipeline/runner.py` — 更新 `_invalidate_cache` 清除 `api:*` 缓存
- [x] 7. `tests/api/test_cities.py` — 7 个城市/区县接口测试全部通过
- [x] 8. `tests/api/test_prices.py` — 11 个价格接口测试全部通过

## 验证

```bash
cd backend
PYTHONPATH=. uv run pytest tests/api/ -v -m slow   # 18 passed
```
