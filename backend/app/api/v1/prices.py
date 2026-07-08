import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cache, get_session
from app.models.city import City
from app.models.district import District
from app.models.price_distribution import PriceDistribution
from app.models.price_snapshot import PriceSnapshot
from app.schemas.price import DistributionItem, DistrictOverviewItem, TrendPoint
from app.services.price_select import select_merged_snapshots

router = APIRouter(prefix="/prices", tags=["prices"])

CACHE_TTL_PRICES = 1800


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


@router.get("/trend", response_model=list[TrendPoint])
async def price_trend(
    region_type: str = Query(..., pattern="^(city|district)$"),
    region_id: int = Query(..., gt=0),
    months: int | None = Query(None, gt=0, le=120),
    db: AsyncSession = Depends(get_session),
    cache: Redis = Depends(get_cache),
):
    cache_key = f"api:trend:{region_type}:{region_id}"
    cached = await cache.get(cache_key)
    if cached:
        points = json.loads(cached)
        if months:
            points = points[-months:]
        return points

    # 多源同月按优先级合并（月度 > 年度挂牌），保持"每月一点"的响应形状
    snaps = await select_merged_snapshots(db, region_type, [region_id])
    points = [TrendPoint.model_validate(r) for r in snaps]

    await cache.set(
        cache_key,
        json.dumps([p.model_dump() for p in points], cls=_DecimalEncoder),
        ex=CACHE_TTL_PRICES,
    )
    if months:
        points = points[-months:]
    return points


@router.get("/distribution", response_model=list[DistributionItem])
async def price_distribution(
    region_type: str = Query(..., pattern="^(city|district)$"),
    region_id: int = Query(..., gt=0),
    year_month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_session),
    cache: Redis = Depends(get_cache),
):
    if year_month is None:
        latest = await db.execute(
            select(func.max(PriceDistribution.year_month)).where(
                PriceDistribution.region_type == region_type,
                PriceDistribution.region_id == region_id,
            )
        )
        year_month = latest.scalar()
        if year_month is None:
            return []

    cache_key = f"api:dist:{region_type}:{region_id}:{year_month}"
    cached = await cache.get(cache_key)
    if cached:
        return json.loads(cached)

    stmt = (
        select(PriceDistribution)
        .where(
            PriceDistribution.region_type == region_type,
            PriceDistribution.region_id == region_id,
            PriceDistribution.year_month == year_month,
        )
        .order_by(PriceDistribution.price_range_low)
    )
    result = await db.execute(stmt)
    items = [DistributionItem.model_validate(r) for r in result.scalars()]

    await cache.set(
        cache_key,
        json.dumps([i.model_dump() for i in items], cls=_DecimalEncoder),
        ex=CACHE_TTL_PRICES,
    )
    return items


@router.get("/overview", response_model=list[DistrictOverviewItem])
async def district_overview(
    city_code: str = Query(...),
    db: AsyncSession = Depends(get_session),
    cache: Redis = Depends(get_cache),
):
    cache_key = f"api:overview:{city_code}"
    cached = await cache.get(cache_key)
    if cached:
        return json.loads(cached)

    city = (await db.execute(select(City).where(City.code == city_code))).scalar_one_or_none()
    if city is None:
        raise HTTPException(status_code=404, detail="城市不存在")

    districts = (await db.execute(
        select(District).where(District.city_id == city.id)
    )).scalars().all()

    items = []
    for d in districts:
        latest_month = (await db.execute(
            select(func.max(PriceSnapshot.year_month)).where(
                PriceSnapshot.region_type == "district",
                PriceSnapshot.region_id == d.id,
            )
        )).scalar()

        snap = None
        if latest_month:
            snap = (await db.execute(
                select(PriceSnapshot).where(
                    PriceSnapshot.region_type == "district",
                    PriceSnapshot.region_id == d.id,
                    PriceSnapshot.year_month == latest_month,
                )
            )).scalar_one_or_none()

        items.append(DistrictOverviewItem(
            id=d.id,
            name=d.name,
            code=d.code,
            supply_price=snap.supply_price if snap else None,
            attention_price=snap.attention_price if snap else None,
            value_price=snap.value_price if snap else None,
        ))

    await cache.set(
        cache_key,
        json.dumps([i.model_dump() for i in items]),
        ex=CACHE_TTL_PRICES,
    )
    return items
