# 代理IP池批量爬取全量城市数据并写入Seed

## Goal

项目运行时手动采集数据过于缓慢，且容易触发 IP 限流/反爬。本任务通过隧道代理批量爬取 creprice.cn 全部 368 个城市及其区县的房价数据，写入 seed JSON 文件，使项目部署后启动即有完整数据，无需等待采集。

## Requirements

### 1. 爬虫脚本（`backend/scripts/seed_scraper.py`）

- 复用现有 `CrepriceSource` 的 `_parse_*` 静态方法（解析城市区县 HTML、价格时间线 JSON、价格分布 JSON）
- HTTP 层替换为 `aiohttp` 异步客户端，支持隧道代理
- 令牌桶速率限制器，控制每秒请求数（默认 5 req/s，可通过 `--rate` 参数调整）
- 代理传入方式：`--proxy` 命令行参数优先，fallback 到 `SEED_PROXY` 环境变量，都没有则直连
- 带 UA 轮换（复用现有 UA 列表）、指数退避重试

### 2. 数据范围

- 区县列表：每个城市的区县名称与 code
- 价格时间线：`sinceyear=1`（API 免费上限，约 13 个月），含供给价/关注价/价值价
- 价格分布：当前价格区间桶占比
- 数据覆盖城市级和区县级

### 3. Seed 文件格式

- 按城市分片存储：`backend/seed/prices/{city_code}.json`
- 每个文件包含该城市的区县列表、城市级与区县级的价格时间线和价格分布
- JSON 格式需与现有 `_parse_*` 方法的输出结构一致

### 4. 断点续爬

- 默认行为（`--resume` 可省略）：检查每个城市的 seed 文件是否已包含当月数据，有则跳过，无则爬取
- 爬完一个城市的所有数据后原子性写入 seed 文件（避免半成品）
- 新数据与已有 seed 文件合并（保留历史月份，追加新月份）

### 5. Seed 加载器

- 在 `lifespan` 启动流程中新增 seed 价格数据加载
- `app_setting` 表记录 `seed_version`，只在版本变化时重新加载
- 加载时使用 `INSERT ... ON CONFLICT DO NOTHING`，只补缺不覆盖
- 加载顺序：先 seed 区县，再 seed 价格数据（外键依赖）

### 6. 依赖管理

- `aiohttp` 加入 dev 依赖组（`[dependency-groups]` dev）
- `aiohttp[socks]` 如果需要 SOCKS 代理支持

## Constraints

- creprice.cn 免费 API 限制：`sinceyear >= 2` 返回 `isAllow: 0`，只能拿 1 年数据
- 代理限制（青果网络免费试用）：1 秒 5 请求、5Mbps 带宽
- 本机无 Docker，脚本需能通过 `uv run python scripts/seed_scraper.py` 独立运行
- Seed 文件提交到 Git 仓库（预估 2-7MB）

## Acceptance Criteria

- [ ] `uv run python scripts/seed_scraper.py --proxy <url>` 能完整爬取 368 个城市的数据并写入 `backend/seed/prices/` 目录
- [ ] 爬取过程中断后重新运行，自动跳过已有当月数据的城市
- [ ] Seed JSON 文件格式正确，包含区县、价格时间线、价格分布
- [ ] 项目启动时，`seed_version` 变化触发 seed 加载，数据正确写入 `district`、`price_snapshot`、`price_distribution` 表
- [ ] 已有数据不被 seed 覆盖（`ON CONFLICT DO NOTHING`）
- [ ] `aiohttp` 在 dev 依赖组，不影响生产依赖
- [ ] 速率限制器正常工作，不超过配置的请求频率
