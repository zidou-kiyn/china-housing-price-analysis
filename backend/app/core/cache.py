from redis.asyncio import Redis

from app.core.config import settings

redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> Redis:
    return redis_client


# 数据入库后需要失效的 API 缓存模式；新增 api:* 缓存 key 时必须同步补充这里
def _api_cache_patterns(city_code: str) -> tuple[str, ...]:
    return (
        "api:cities",
        f"api:districts:{city_code}",
        f"api:overview:{city_code}",
        "api:trend:*",
        "api:dist:*",
        "api:rank:*",
        "api:compare:*",
        "api:mapheat:*",
    )


async def invalidate_api_caches(redis: Redis, city_code: str) -> int:
    """删除受 city_code 数据入库影响的全部 API 缓存 key，返回删除数量。"""
    keys = []
    for pattern in _api_cache_patterns(city_code):
        async for key in redis.scan_iter(pattern):
            keys.append(key)
    if keys:
        await redis.delete(*keys)
    return len(keys)


async def flush_all_api_caches(redis: Redis) -> int:
    """删除所有 api:* 缓存 key（seed 全量重导等全站数据变更后使用）。"""
    keys = [key async for key in redis.scan_iter("api:*")]
    if keys:
        await redis.delete(*keys)
    return len(keys)
