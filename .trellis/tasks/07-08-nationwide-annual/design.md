# Design — 全国城市年度房价导入（child E）

## 为什么用独立批量导入（不走 PipelineRunner）

`PipelineRunner.run(source, city_code)` 按 **creprice city_code** 逐城爬取；本数据集按**城市名**、一次含全国所有城市。阻抗不匹配（源无法把 creprice code 反查成 CSV 名）。故用**独立批量导入**：一次下载 → 全表 name→city_id 匹配 → 批量 upsert。复用 `upsert_price_snapshots`（含 child A 的 `source` 列）。

## 数据源

- URL（GitHub raw，免登录）：
  `https://raw.githubusercontent.com/changao1/70-China-cities-housing-index-data-by-national-bureau-of-statistics/main/supplementary/58tongcheng_city_avg_price_annual_2010-2024.csv`
  anjuke：同目录 `anjuke_city_avg_price_annual_2015-2024.csv`
- 缓存目录：`data/listing/`（`data/` 已 gitignore）。

## 组件

### 1. `app/collector/sources/listing_annual.py`（下载+解析，纯逻辑，可测）
```python
SOURCES = {
  "58":     (".../58tongcheng_city_avg_price_annual_2010-2024.csv", "listing_annual_58"),
  "anjuke": (".../anjuke_city_avg_price_annual_2015-2024.csv",     "listing_annual_anjuke"),
}
def download_csv(source_key, cache_dir=None) -> Path        # 已缓存则复用
def parse_annual_csv(text) -> list[dict]                    # {province, city, year:int, price:int}
    # 跳过空/非法 price；price 合理区间 500..300000
```

### 2. `app/services/nationwide_import.py`（DB 导入）
```python
async def import_annual(session, source_key="58") -> dict:
    rows = parse_annual_csv(download_csv(source_key).read_text())
    # 城市名 → city_id（精确名匹配现有 city 表；未匹配记入 skipped）
    name_to_id = { name: id for id,name in await session: SELECT id,name FROM city }
    # 按 city 分组 → 年度记录：year_month=f"{year}-12", supply_price=price, sample_count=None
    # 每城 upsert_price_snapshots(session, recs, "city", city_id, source=SOURCES[source_key][1])
    # 统计 matched/skipped/snapshots；skipped 城市名清单返回
    # 结束后 invalidate_api_caches（或直接 del api:cities + api:trend:*）
    return {"matched": n, "skipped": [...], "snapshots": total, "source": ...}
```
> year_month 用 `YYYY-12`（年度值落当年 12 月，约定）。与 creprice 月度 upsert 冲突时 latest-wins + source 标记；正常无冲突（creprice 缺这些城/月）。

### 3. 管理端触发（二选一）
- 简单：`POST /admin/collect/import-annual` body `{source:"58"|"anjuke"}` → 同步跑（~3400 行、~330 城、一次 bulk，<2s），返回覆盖统计。放 `admin_collect.py`。
- 或复用 job_runner 起后台任务（与现有 collect 一致，进度可查）。MVP 用同步端点即可。

### 4. schema
`AnnualImportRequest{source:str="58"}`、`AnnualImportResult{source, matched, skipped_count, skipped_cities:list[str], snapshots}`。

## 前端（可选增强）
覆盖表/首页已能显示（child C 已让 `/cities` 纳入"有城市级快照"的城市）。导入后 ~330 城自动出现在首页选择器。可在数据管理页加个"导入全国年度数据"按钮调用端点。

## 兼容/回滚
- 纯新增：新 source_key 的快照，不动 creprice/kaggle。
- 回滚：`DELETE FROM price_snapshot WHERE source IN ('listing_annual_58','listing_annual_anjuke')`。
- 幂等：upsert on (region_type,region_id,year_month)，重跑覆盖同值。
