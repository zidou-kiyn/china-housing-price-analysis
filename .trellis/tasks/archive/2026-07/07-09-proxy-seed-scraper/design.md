# 技术设计：代理IP池批量爬取 Seed

## 架构概览

```
seed_scraper.py (独立入口)
  ├── AsyncHttpClient (aiohttp + 隧道代理 + UA轮换 + 重试)
  ├── TokenBucketRateLimiter (令牌桶限速)
  ├── CrepriceSource._parse_* (复用现有解析逻辑)
  ├── SeedFileManager (读写/合并 seed JSON)
  └── Orchestrator (调度368城市的并发爬取)
```

## 模块设计

### 1. TokenBucketRateLimiter

```python
class TokenBucketRateLimiter:
    def __init__(self, rate: float = 5.0, capacity: float = 5.0)
    async def acquire(self) -> None  # 等待直到有令牌可用
```

- `rate`：每秒补充的令牌数
- `capacity`：桶容量（允许的最大突发数）
- 基于 `asyncio.Event` + 时间差计算令牌数，无需后台任务

### 2. AsyncHttpClient

```python
class AsyncHttpClient:
    def __init__(self, proxy: str | None, rate_limiter: TokenBucketRateLimiter,
                 max_retries: int = 3, timeout: float = 15.0)
    async def get(self, url: str, params: dict | None = None) -> aiohttp.ClientResponse
```

- 每次请求前调用 `rate_limiter.acquire()`
- 随机选择 UA（复用 `CrawlerHttpClient.UA_LIST`）
- 失败时指数退避重试，区分可重试错误（429、5xx、网络超时）和不可重试错误（404）
- 通过 `aiohttp.ClientSession` 的 proxy 参数传入隧道代理 URL

### 3. SeedFileManager

```python
class SeedFileManager:
    def __init__(self, seed_dir: Path)  # backend/seed/prices/
    def should_scrape(self, city_code: str, current_month: str) -> bool
    def read_existing(self, city_code: str) -> dict | None
    def write(self, city_code: str, data: dict) -> None
    def merge_timelines(self, old: list[dict], new: list[dict]) -> list[dict]
```

- `should_scrape`：检查 `{city_code}.json` 是否存在且包含 `current_month` 的数据
- `merge_timelines`：按 `year_month` 合并，保留历史月份，新数据追加
- `write`：先写临时文件再 rename，保证原子性

### 4. Seed JSON 文件结构

```json
{
  "city_code": "bj",
  "city_name": "北京",
  "province": "北京",
  "scraped_at": "2026-07-09T10:00:00",
  "districts": [
    {"name": "朝阳", "code": "cy", "city_code": "bj"}
  ],
  "price_timeline": {
    "city": [
      {"year_month": "2025-07", "supply_price": 39070, "attention_price": 65796, "value_price": 39070, "sample_count": 15243}
    ],
    "districts": {
      "cy": [...]
    }
  },
  "price_distribution": {
    "city": [
      {"price_range_low": 6000, "price_range_high": 7000, "percentage": 12.5}
    ],
    "districts": {
      "cy": [...]
    }
  }
}
```

### 5. Orchestrator（主调度流程）

```
1. 读取 backend/seed/cities.json 获取 368 个城市列表
2. 对每个城市:
   a. should_scrape() 检查是否需要爬取
   b. 爬取区县列表（1 个请求）
   c. 爬取城市级价格时间线 + 价格分布（2 个请求）
   d. 爬取每个区县的价格时间线 + 价格分布（2N 个请求）
   e. 合并已有数据，原子写入 seed 文件
3. 汇总统计（成功/跳过/失败城市数）
```

并发模型：用 `asyncio.Semaphore` 控制同时处理的城市数（建议 3-5 个），令牌桶在请求层面控制实际发送速率。两层控制互不干扰。

### 6. Seed 加载器（应用启动）

修改 `backend/app/services/seed.py`，新增：

```python
async def seed_prices_if_needed(session: AsyncSession) -> None:
    current_version = _compute_seed_version()  # 基于 seed 文件的内容哈希或目录 mtime
    stored_version = await _get_setting(session, "seed_price_version")
    if stored_version == current_version:
        return
    # 1. 加载区县 seed
    # 2. 加载价格时间线 seed（INSERT ON CONFLICT DO NOTHING）
    # 3. 加载价格分布 seed（INSERT ON CONFLICT DO NOTHING）
    # 4. 更新 seed_price_version
```

`_compute_seed_version()`：对 `backend/seed/prices/` 目录下所有文件的修改时间取最大值，格式化为版本字符串。简单可靠。

### 7. 数据流 & 外键关系

```
seed_cities_if_empty() → city 表（已有）
    ↓
seed_prices_if_needed() → district 表（FK → city.id, 需先通过 city_code 查 city.id）
    ↓
                        → price_snapshot 表（region_type + region_id, 需先查 city.id / district.id）
    ↓
                        → price_distribution 表（同上）
```

加载器需要先查询 city 表建立 `code → id` 映射，再查询/插入 district 建立 `(city_code, district_code) → district.id` 映射，最后用这些 ID 插入价格数据。

## 兼容性

- 不修改现有 `CrepriceScraper` 类的任何代码，只 import 其 `_parse_*` 静态方法
- 不修改现有 `CrawlerHttpClient`，新脚本使用独立的 `AsyncHttpClient`
- Seed 加载器在 `seed_cities_if_empty()` 之后执行，保证 city 表已有数据
- 现有采集流程（管理后台触发）不受影响
