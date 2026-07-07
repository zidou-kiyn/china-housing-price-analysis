# 执行计划 - creprice 采集适配器

## 步骤

- [ ] 1. `collector/base.py` — BaseSource ABC + RawRecord dataclass + SourceRegistry
- [ ] 2. `collector/http_client.py` — 封装 requests：UA 轮换列表 + random delay(1~3s) + 指数退避重试(max 3)
- [ ] 3. `collector/storage.py` — save_raw(source, city_code, data) → `data/raw/{source}/{city}/{YYYY-MM-DD}.json`
- [ ] 4. `collector/sources/creprice.py` — CrepriceSource：
  - `fetch_cities()` → 解析 `/rank/citySel.html` HTML，regex 提取 `a.city` 和 `a.dist`，按 code 去重
  - `fetch_price_timeline(city_code, district_code="allsq1")` → 调 JSON API `chartsdatanew.html?based=price&dtype=line`
  - `parse_price_timeline(json_data)` → 从 `data[0].rows` 取 supply(value)，`data[1].rows` 取 attention，`data[2].rows` 取 value_price，按 month 对齐合并
  - `fetch_price_distribution(city_code, district_code)` → 调 JSON API `dtype=bar`
  - `parse_price_distribution(json_data)` → 从 section 解析 low/high，data 为 percentage
- [ ] 5. `tests/collector/fixtures/` — 复制真实 API 响应 JSON 作为测试 fixture
- [ ] 6. `tests/collector/test_creprice_parse.py` — 解析逻辑单元测试
- [ ] 7. `tests/collector/test_creprice_live.py` — 网络集成冒烟测试（@pytest.mark.slow）

## 关键实现细节

- series[0] chartsName=供给: `rows[].value` = supply_price, `rows[].count` = sample_count
- series[1] chartsName=关注: `rows[].data` = attention_price（部分月份无此 key）
- series[2] chartsName=价值: `rows[].data` = value_price
- 缺失数据：key 不存在，用 `.get()` 返回 None
- 城市列表 HTML 正则：`r'<a class="city[^"]*"[^>]*href="/city/([^"]+)\.html">([^<]+)</a>'`
- 区县列表 HTML 正则：`r'<a class="dist"[^>]*href="/district/([^"]+)\.html\?city=([^"]+)">([^<]+)</a>'`

## 验证

```bash
cd backend
uv run pytest tests/collector/test_creprice_parse.py -v
uv run pytest tests/collector/test_creprice_live.py -v -m slow
```
