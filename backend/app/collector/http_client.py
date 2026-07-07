"""爬虫 HTTP 客户端：轮换 User-Agent、随机限速、指数退避重试。

creprice.cn 在无 User-Agent 时会在 TLS 层直接断连，因此每次请求必须带浏览器 UA。
"""

from __future__ import annotations

import logging
import random
import time

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class CrawlerHttpClient:
    """带限速与重试的同步 HTTP 客户端。"""

    UA_LIST = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ]

    def __init__(
        self,
        delay_min: float | None = None,
        delay_max: float | None = None,
        max_retries: int | None = None,
        backoff_base: float = 2.0,
        timeout: float = 15.0,
        session: requests.Session | None = None,
        proxy: str | None | bool = None,
    ) -> None:
        self.delay_min = settings.crawl_request_delay_min if delay_min is None else delay_min
        self.delay_max = settings.crawl_request_delay_max if delay_max is None else delay_max
        self.max_retries = settings.crawl_max_retries if max_retries is None else max_retries
        self.backoff_base = backoff_base
        self.timeout = timeout
        self.session = session or requests.Session()

        # proxy=None（默认）自动读管理端「采集代理」设置；False 强制直连；字符串显式指定
        if proxy is None:
            from app.services.app_settings import get_proxy_url_sync

            proxy = get_proxy_url_sync()
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        """GET 请求：随机限速 + 随机 UA + 指数退避重试。失败到达上限则抛出最后一次异常。"""
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._sleep_delay()
            headers = {"User-Agent": random.choice(self.UA_LIST)}
            try:
                response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
                logger.info("GET %s -> %s", response.url, response.status_code)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(
                    "请求失败 (第 %d/%d 次): %s", attempt, self.max_retries, exc
                )
                if attempt < self.max_retries:
                    time.sleep(self.backoff_base * (2 ** (attempt - 1)))

        assert last_exc is not None
        raise last_exc

    def _sleep_delay(self) -> None:
        time.sleep(random.uniform(self.delay_min, self.delay_max))
