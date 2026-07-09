"""代理IP池批量爬取全量城市房价数据并写入 seed。

隧道代理 + 令牌桶限速 + 异步并发，复用 CrepriceSource 的 _parse_* 解析逻辑，
按城市分片写入 backend/seed/prices/{city_code}.json。启动时由 seed_prices_if_needed
只补缺不覆盖地导入数据库。

用法：
    uv run python scripts/seed_scraper.py --proxy http://user:pass@host:port
    uv run python scripts/seed_scraper.py --proxy socks5://user:pass@host:port --cities bj,sh
    uv run python scripts/seed_scraper.py --rate 5 --concurrency 3

代理优先级：--proxy > 环境变量 SEED_PROXY > 直连。默认断点续爬（本月已完整爬过的城市跳过）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.collector.http_client import CrawlerHttpClient  # noqa: E402
from app.collector.sources.creprice import CrepriceSource  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402

logger = logging.getLogger("seed_scraper")

_BASE_URL = CrepriceSource.BASE_URL
_SEED_DIR = Path(__file__).resolve().parent.parent / "seed" / "prices"
_CITIES_FILE = Path(__file__).resolve().parent.parent / "seed" / "cities.json"

# creprice 图表 API：时序 dtype=line（sinceyear=1 免费上限约 13 个月），分布 dtype=bar。
_CHARTS_URL = f"{_BASE_URL}/market/chartsdatanew.html"
_CITY_DISTRICT = "allsq1"  # 城市级时序 / 分布的 district 占位

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class _RetryableError(Exception):
    """可重试的 HTTP 状态（429/5xx）。"""


def _timeline_params(city_code: str, district_code: str) -> dict[str, str]:
    return {
        "city": city_code,
        "district": district_code,
        "proptype": "11",
        "flag": "1",
        "type": "forsale",
        "based": "price",
        "dtype": "line",
        "sinceyear": "1",
        "timeType": "month",
    }


def _distribution_params(city_code: str, district_code: str) -> dict[str, str]:
    return {
        "city": city_code,
        "district": district_code,
        "proptype": "11",
        "flag": "1",
        "type": "forsale",
        "based": "price",
        "dtype": "bar",
    }


class TokenBucketRateLimiter:
    """令牌桶限速器：按时间差补充令牌，acquire() 阻塞至有令牌可用。

    加锁串行化 acquire，使整体请求速率不超过 rate（跨并发城市任务共享一个实例）。
    """

    def __init__(self, rate: float = 5.0, capacity: float | None = None) -> None:
        self.rate = rate
        self.capacity = rate if capacity is None else capacity
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(
                    self.capacity, self._tokens + (now - self._updated) * self.rate
                )
                self._updated = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self.rate)


class AsyncHttpClient:
    """aiohttp 异步客户端：隧道代理 + UA 轮换 + 令牌桶限速 + 指数退避重试。

    http(s) 代理通过每请求 proxy 参数传入；socks 代理通过 aiohttp_socks 连接器
    在 session 层生效。区分可重试（429/5xx/网络超时）与不可重试（其余 4xx）错误。
    """

    UA_LIST = CrawlerHttpClient.UA_LIST

    def __init__(
        self,
        proxy: str | None,
        rate_limiter: TokenBucketRateLimiter,
        max_retries: int = 3,
        timeout: float = 15.0,
        backoff_base: float = 2.0,
    ) -> None:
        self.rate_limiter = rate_limiter
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._request_proxy: str | None = None
        self._connector: aiohttp.BaseConnector | None = None
        self._session: aiohttp.ClientSession | None = None

        if proxy:
            scheme = urlsplit(proxy).scheme.lower()
            if scheme in ("http", "https"):
                self._request_proxy = proxy
            elif scheme.startswith("socks"):
                from aiohttp_socks import ProxyConnector

                self._connector = ProxyConnector.from_url(proxy)
            else:
                raise ValueError(f"不支持的代理协议: {scheme}（仅 http/https/socks*）")

    async def __aenter__(self) -> AsyncHttpClient:
        self._session = aiohttp.ClientSession(
            connector=self._connector, timeout=self._timeout
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._session is not None:
            await self._session.close()

    async def get_text(self, url: str, params: dict[str, str] | None = None) -> str:
        assert self._session is not None, "AsyncHttpClient 须在 async with 内使用"
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            await self.rate_limiter.acquire()
            headers = {"User-Agent": random.choice(self.UA_LIST)}
            try:
                async with self._session.get(
                    url, params=params, headers=headers, proxy=self._request_proxy
                ) as resp:
                    if resp.status >= 400:
                        await resp.read()
                        if resp.status in _RETRYABLE_STATUS:
                            raise _RetryableError(f"HTTP {resp.status}")
                        raise RuntimeError(f"HTTP {resp.status} for {resp.url}")
                    return await resp.text()
            except (_RetryableError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                logger.warning("请求失败 (第 %d/%d 次) %s: %s", attempt, self.max_retries, url, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_base * (2 ** (attempt - 1)))

        assert last_exc is not None
        raise last_exc

    async def get_json(self, url: str, params: dict[str, str] | None = None) -> dict:
        # creprice 的 JSON 接口 content-type 不稳定，取文本后自行解析。
        return json.loads(await self.get_text(url, params=params))


class SeedFileManager:
    """读写 / 合并 backend/seed/prices/{city_code}.json，原子写入。"""

    def __init__(self, seed_dir: Path = _SEED_DIR) -> None:
        self.seed_dir = seed_dir

    def _path(self, city_code: str) -> Path:
        return self.seed_dir / f"{city_code}.json"

    def read_existing(self, city_code: str) -> dict | None:
        path = self._path(city_code)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def should_scrape(self, city_code: str, current_month: str) -> bool:
        """本月已完整爬过（scraped_at 落在 current_month）则跳过。"""
        data = self.read_existing(city_code)
        if data is None:
            return True
        return not str(data.get("scraped_at", "")).startswith(current_month)

    @staticmethod
    def merge_timelines(old: list[dict], new: list[dict]) -> list[dict]:
        """按 year_month 合并：保留历史月份，新数据覆盖同月。"""
        by_month = {row["year_month"]: row for row in old}
        for row in new:
            by_month[row["year_month"]] = row
        return [by_month[m] for m in sorted(by_month)]

    def write(self, city_code: str, data: dict) -> None:
        self.seed_dir.mkdir(parents=True, exist_ok=True)
        target = self._path(city_code)
        tmp = target.with_name(f"{city_code}.json.tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(target)


@dataclass
class SeedCity:
    code: str
    name: str
    province: str | None


class Orchestrator:
    """调度全量城市的并发爬取：区县 + 城市级/区县级时序 + 分布，合并后原子写入。"""

    def __init__(
        self,
        client: AsyncHttpClient,
        files: SeedFileManager,
        concurrency: int,
    ) -> None:
        self.client = client
        self.files = files
        self.semaphore = asyncio.Semaphore(concurrency)
        self.current_month = datetime.now().strftime("%Y-%m")

    async def run(self, cities: list[SeedCity]) -> dict[str, int]:
        results = await asyncio.gather(
            *(self._scrape_city(city) for city in cities)
        )
        summary = {"scraped": 0, "skipped": 0, "failed": 0}
        for status in results:
            summary[status] += 1
        return summary

    async def _scrape_city(self, city: SeedCity) -> str:
        async with self.semaphore:
            if not self.files.should_scrape(city.code, self.current_month):
                logger.info("跳过 %s（本月已爬）", city.code)
                return "skipped"
            try:
                data = await self._collect_city(city)
            except Exception as exc:
                logger.error("城市 %s 爬取失败: %s", city.code, exc)
                return "failed"
            self.files.write(city.code, data)
            logger.info(
                "完成 %s：%d 区县，%d 月时序",
                city.code,
                len(data["districts"]),
                len(data["price_timeline"]["city"]),
            )
            return "scraped"

    async def _collect_city(self, city: SeedCity) -> dict:
        html = await self.client.get_text(f"{_BASE_URL}/city/{city.code}.html")
        districts = CrepriceSource._parse_city_districts(html, city.code)

        city_timeline = await self._fetch_timeline(city.code, _CITY_DISTRICT)
        city_distribution = await self._fetch_distribution(city.code, _CITY_DISTRICT)

        district_timeline: dict[str, list[dict]] = {}
        district_distribution: dict[str, list[dict]] = {}
        for dist in districts:
            district_timeline[dist.code] = await self._fetch_timeline(
                city.code, dist.code
            )
            district_distribution[dist.code] = await self._fetch_distribution(
                city.code, dist.code
            )

        existing = self.files.read_existing(city.code)
        if existing is not None:
            city_timeline = SeedFileManager.merge_timelines(
                existing.get("price_timeline", {}).get("city", []), city_timeline
            )
            old_dist_tl = existing.get("price_timeline", {}).get("districts", {})
            for code, timeline in district_timeline.items():
                district_timeline[code] = SeedFileManager.merge_timelines(
                    old_dist_tl.get(code, []), timeline
                )

        return {
            "city_code": city.code,
            "city_name": city.name,
            "province": city.province,
            "scraped_at": datetime.now().isoformat(timespec="seconds"),
            "districts": [
                {"name": d.name, "code": d.code, "city_code": d.city_code}
                for d in districts
            ],
            "price_timeline": {
                "city": city_timeline,
                "districts": district_timeline,
            },
            "price_distribution": {
                "city": city_distribution,
                "districts": district_distribution,
            },
        }

    async def _fetch_timeline(self, city_code: str, district_code: str) -> list[dict]:
        payload = await self.client.get_json(
            _CHARTS_URL, params=_timeline_params(city_code, district_code)
        )
        return CrepriceSource._parse_price_timeline(payload)

    async def _fetch_distribution(
        self, city_code: str, district_code: str
    ) -> list[dict]:
        payload = await self.client.get_json(
            _CHARTS_URL, params=_distribution_params(city_code, district_code)
        )
        return CrepriceSource._parse_price_distribution(payload)


def _load_cities(codes: list[str] | None) -> list[SeedCity]:
    raw = json.loads(_CITIES_FILE.read_text(encoding="utf-8"))
    cities = [
        SeedCity(code=c["code"], name=c["name"], province=c.get("province"))
        for c in raw
    ]
    if codes:
        wanted = set(codes)
        cities = [c for c in cities if c.code in wanted]
    return cities


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="代理IP池批量爬取全量城市房价数据并写入 seed",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="隧道代理 URL（http(s):// 或 socks5://），优先于环境变量 SEED_PROXY",
    )
    parser.add_argument(
        "--rate", type=float, default=5.0, help="每秒最大请求数（默认 5）"
    )
    parser.add_argument(
        "--concurrency", type=int, default=3, help="并发处理的城市数（默认 3）"
    )
    parser.add_argument(
        "--cities",
        default=None,
        help="逗号分隔的城市 code 列表（仅爬这些，缺省爬全部）",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="断点续爬（默认行为，本月已爬过的城市自动跳过）",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    proxy = args.proxy or os.environ.get("SEED_PROXY") or None
    codes = [c.strip() for c in args.cities.split(",") if c.strip()] if args.cities else None
    cities = _load_cities(codes)
    if not cities:
        logger.error("没有匹配的城市（--cities=%s）", args.cities)
        return 1

    logger.info(
        "开始爬取 %d 城市｜代理=%s｜rate=%.1f/s｜concurrency=%d",
        len(cities),
        "直连" if not proxy else urlsplit(proxy).scheme,
        args.rate,
        args.concurrency,
    )

    rate_limiter = TokenBucketRateLimiter(rate=args.rate)
    async with AsyncHttpClient(proxy, rate_limiter) as client:
        orchestrator = Orchestrator(client, SeedFileManager(), args.concurrency)
        summary = await orchestrator.run(cities)

    logger.info(
        "全部结束：成功=%d 跳过=%d 失败=%d",
        summary["scraped"],
        summary["skipped"],
        summary["failed"],
    )
    return 1 if summary["failed"] else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    setup_logging()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
