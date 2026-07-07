import json

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cache, get_session
from app.models.city import City
from app.models.district import District
from app.models.price_snapshot import PriceSnapshot
from app.schemas.city import CityOut, DistrictOut

router = APIRouter(prefix="/cities", tags=["cities"])

CACHE_TTL_CITIES = 3600


@router.get("", response_model=list[CityOut])
async def list_cities(
    db: AsyncSession = Depends(get_session),
    cache: Redis = Depends(get_cache),
):
    cached = await cache.get("api:cities")
    if cached:
        return json.loads(cached)

    # 返回可分析的城市：有区县数据，或有城市级价格快照（如 Kaggle 城市级历史源覆盖但无区县的城市）。
    # 全国城市目录见管理端 /admin/collect/cities
    has_city_snapshot = (
        select(PriceSnapshot.id)
        .where(
            PriceSnapshot.region_type == "city",
            PriceSnapshot.region_id == City.id,
        )
        .exists()
    )
    result = await db.execute(
        select(City)
        .where(or_(City.districts.any(), has_city_snapshot))
        .order_by(City.name)
    )
    cities = [CityOut.model_validate(c) for c in result.scalars()]
    await cache.set("api:cities", json.dumps([c.model_dump() for c in cities]), ex=CACHE_TTL_CITIES)
    return cities


@router.get("/{city_code}/districts", response_model=list[DistrictOut])
async def list_districts(
    city_code: str,
    db: AsyncSession = Depends(get_session),
    cache: Redis = Depends(get_cache),
):
    cache_key = f"api:districts:{city_code}"
    cached = await cache.get(cache_key)
    if cached:
        return json.loads(cached)

    city = (await db.execute(select(City).where(City.code == city_code))).scalar_one_or_none()
    if city is None:
        raise HTTPException(status_code=404, detail="城市不存在")

    result = await db.execute(
        select(District).where(District.city_id == city.id).order_by(District.name)
    )
    districts = [DistrictOut.model_validate(d) for d in result.scalars()]
    await cache.set(cache_key, json.dumps([d.model_dump() for d in districts]), ex=CACHE_TTL_CITIES)
    return districts
