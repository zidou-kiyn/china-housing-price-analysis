"""缓存失效单元测试：入库后 API 缓存 key 被清除（不依赖真实 Redis）。"""

import fnmatch

import pytest

from app.core.cache import invalidate_api_caches, redis_client
from app.pipeline.runner import PipelineRunner

pytestmark = pytest.mark.asyncio


class FakeRedis:
    def __init__(self, keys):
        self.keys = set(keys)

    async def scan_iter(self, pattern):
        for key in sorted(self.keys):
            if fnmatch.fnmatchcase(key, pattern):
                yield key

    async def delete(self, *keys):
        self.keys -= set(keys)
        return len(keys)


class BrokenRedis:
    def scan_iter(self, pattern):
        raise ConnectionError("redis down")


async def test_invalidates_all_api_key_families():
    fake = FakeRedis({
        "api:cities",
        "api:districts:qz",
        "api:overview:qz",
        "api:trend:city:403",
        "api:dist:district:1:2026-07",
        "api:rank:district:qz:avg_price:desc",
        "api:compare:district:1,2:avg",
        "api:mapheat:qz:district",
    })
    deleted = await invalidate_api_caches(fake, "qz")
    assert deleted == 8
    assert fake.keys == set()


async def test_keeps_other_city_and_unrelated_keys():
    fake = FakeRedis({
        "api:cities",
        "api:districts:qz",
        "api:districts:xm",
        "api:overview:xm",
        "session:abc",
    })
    await invalidate_api_caches(fake, "qz")
    assert fake.keys == {"api:districts:xm", "api:overview:xm", "session:abc"}


async def test_runner_defaults_to_global_redis():
    runner = PipelineRunner(session_factory=None)
    assert runner.redis is redis_client


async def test_runner_invalidate_swallows_redis_errors():
    runner = PipelineRunner(session_factory=None, redis=BrokenRedis())
    await runner._invalidate_cache("qz")
