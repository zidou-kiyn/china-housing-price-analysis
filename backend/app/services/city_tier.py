"""城市等级辅助：从 DB 加载 city/district → tier 映射。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.city import City
from app.models.district import District


async def load_city_tier_map(db: AsyncSession) -> dict[int, int | None]:
    """返回 {region_id: tier} 映射，覆盖所有 city 和 district。

    district 继承所属 city 的 tier。
    """
    tier_map: dict[int, int | None] = {}

    rows = (await db.execute(select(City.id, City.tier))).all()
    city_tier_by_id: dict[int, int | None] = {}
    for city_id, tier in rows:
        tier_map[city_id] = tier
        city_tier_by_id[city_id] = tier

    dist_rows = (await db.execute(select(District.id, District.city_id))).all()
    for dist_id, city_id in dist_rows:
        tier_map[dist_id] = city_tier_by_id.get(city_id)

    return tier_map
