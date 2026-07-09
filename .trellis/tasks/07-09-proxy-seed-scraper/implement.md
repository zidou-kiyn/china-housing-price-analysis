# 实现计划：代理IP池批量爬取 Seed

## 实现顺序

### Phase 1：依赖与基础设施

- [x] 1.1 `pyproject.toml` dev 依赖组添加 `aiohttp` + `aiohttp-socks`（aiohttp 无 `socks` extra，SOCKS 支持由独立包 `aiohttp-socks` 的 `ProxyConnector` 提供，与代码 `from aiohttp_socks import ProxyConnector` 匹配）
- [x] 1.2 `uv lock` 更新锁文件（新增 aiohttp/aiohttp-socks 及其传递依赖，均在 dev 组）

### Phase 2：爬虫脚本核心

- [x] 2.1 创建 `backend/scripts/seed_scraper.py`，搭建 CLI 骨架（argparse: `--proxy`, `--rate`, `--concurrency`, `--cities`, `--resume`）
- [x] 2.2 实现 `TokenBucketRateLimiter`（令牌桶，asyncio 原生，锁串行化跨并发共享）
- [x] 2.3 实现 `AsyncHttpClient`（aiohttp + 代理 + UA 轮换 + 指数退避重试）
- [x] 2.4 实现 `SeedFileManager`（seed 文件读写、合并、原子写入、should_scrape 判断）
- [x] 2.5 实现 `Orchestrator`（主调度：遍历城市 → 爬取 → 写 seed，asyncio.Semaphore 并发控制）
- [x] 2.6 接入 `CrepriceSource._parse_*` 静态方法做数据解析

### Phase 3：Seed 加载器

- [x] 3.1 `backend/app/services/seed.py` 新增 `seed_prices_if_needed()` 函数
- [x] 3.2 实现 seed_version 计算逻辑（基于 seed 目录文件数 + mtime 最大值）
- [x] 3.3 实现区县 seed 加载（查 city.id 映射 → 批量插入 district）
- [x] 3.4 实现价格时间线 seed 加载（查 region_id → INSERT ON CONFLICT DO NOTHING）
- [x] 3.5 实现价格分布 seed 加载（同上）
- [x] 3.6 `backend/app/main.py` lifespan 中添加 `seed_prices_if_needed()` 调用（在 `seed_cities_if_empty()` 之后）

### Phase 4：验证

- [x] 4.1 本机用 `uv run python scripts/seed_scraper.py --cities bj --rate 2 --concurrency 1` 无代理直连测试单城市爬取（主会话冒烟测试成功）；随后用户提供隧道代理 `http://tun-ytljxq.qg.net:14432` 跑通全量 368 城市（分 4 轮：252→59→56→1 成功，断点续爬每轮自动跳过已完成城市直至收敛为 0 失败）
- [x] 4.2 验证断点续爬：中断后重跑，已有城市被跳过（主会话二次运行确认跳过；全量爬取过程中也依赖同一机制从 116 个失败城市收敛到 0）
- [x] 4.3 验证 seed JSON 文件结构正确性（全部 368 个文件通过 JSON 结构校验：均含 city_code/districts/price_timeline/price_distribution，共 2291 个区县，平均每城市 12.2 个月时序，总大小 8.6MB）
- [ ] 4.4 验证 seed 加载器：启动项目后 district / price_snapshot / price_distribution 表有数据（本机无 Postgres/Redis，无法起库实测；已用不依赖 DB 的纯函数走查 + SQL 语义分析代替，待用户在有 DB 环境验证）

补充观察：全量爬取过程中出现周期性 HTTP 456 批量失败（隧道代理出口 IP 被 creprice 反爬机制临时封禁，持续 30-80 秒后恢复），断点续爬机制按设计正常应对，无需修改代码。

## 验证命令

```bash
# 测试单城市爬取
cd backend && uv run python scripts/seed_scraper.py --proxy socks5://user:pass@host:port --cities bj,sh

# 检查生成的 seed 文件
python -c "import json; d=json.load(open('seed/prices/bj.json')); print(len(d['districts']), 'districts'); print(len(d['price_timeline']['city']), 'months')"

# 验证断点续爬（第二次应跳过）
uv run python scripts/seed_scraper.py --proxy socks5://user:pass@host:port --cities bj,sh

# 全量爬取
uv run python scripts/seed_scraper.py --proxy socks5://user:pass@host:port
```

## 风险与回滚

- **风险**：creprice.cn 页面结构变化导致解析失败 → 现有 `_parse_*` 方法已在生产使用，风险可控
- **风险**：代理额度不够跑完 368 城市 → 断点续爬机制保证可分多次完成
- **回滚**：删除 `backend/seed/prices/` 目录 + 移除 lifespan 中的加载调用即可
