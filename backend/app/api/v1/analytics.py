"""排行 / 对比 / 地图热力分析端点。"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cache, get_session
from app.models.city import City
from app.models.district import District
from app.models.price_snapshot import PriceSnapshot
from app.schemas.analytics import (
    CompareRegion,
    CompareResponse,
    MapHeatItem,
    MapHeatResponse,
    RankItem,
    RankResponse,
)

router = APIRouter(tags=["analytics"])

CACHE_TTL_ANALYTICS = 1800


def _shift_month(year_month: str, delta: int) -> str:
    year, month = map(int, year_month.split("-"))
    total = year * 12 + month - 1 + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _pct_change(current: int | None, base: int | None) -> float | None:
    if current is None or not base:
        return None
    return round((current - base) / base * 100, 1)


async def _load_regions(
    db: AsyncSession,
    region_type: str,
    city_code: str | None = None,
    region_ids: list[int] | None = None,
) -> dict[int, str]:
    """按类型加载区域 id → name 映射，city_code 不存在时抛 404。"""
    if region_type == "city":
        stmt = select(City.id, City.name).order_by(City.name)
        if region_ids:
            stmt = stmt.where(City.id.in_(region_ids))
    else:
        stmt = select(District.id, District.name).order_by(District.name)
        if city_code:
            city = (await db.execute(select(City).where(City.code == city_code))).scalar_one_or_none()
            if city is None:
                raise HTTPException(status_code=404, detail="城市不存在")
            stmt = stmt.where(District.city_id == city.id)
        if region_ids:
            stmt = stmt.where(District.id.in_(region_ids))
    rows = (await db.execute(stmt)).all()
    return {row.id: row.name for row in rows}


async def _load_snapshots(
    db: AsyncSession, region_type: str, region_ids: list[int]
) -> dict[int, dict[str, PriceSnapshot]]:
    """加载各区域快照，按 region_id → {year_month: snapshot} 分组。"""
    stmt = select(PriceSnapshot).where(
        PriceSnapshot.region_type == region_type,
        PriceSnapshot.region_id.in_(region_ids),
    )
    result = await db.execute(stmt)
    grouped: dict[int, dict[str, PriceSnapshot]] = {}
    for snap in result.scalars():
        grouped.setdefault(snap.region_id, {})[snap.year_month] = snap
    return grouped


@router.get("/rank", response_model=RankResponse)
async def price_rank(
    region_type: str = Query(..., pattern="^(city|district)$"),
    city_code: str | None = Query(None),
    sort_by: str = Query("supply_price", pattern="^(supply_price|attention_price|value_price)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
    cache: Redis = Depends(get_cache),
):
    cache_key = f"api:rank:{region_type}:{city_code or 'all'}:{sort_by}:{sort_order}"
    cached = await cache.get(cache_key)
    if cached:
        items = json.loads(cached)
    else:
        regions = await _load_regions(db, region_type, city_code=city_code)
        snapshots = await _load_snapshots(db, region_type, list(regions)) if regions else {}

        items = []
        for region_id, name in regions.items():
            months = snapshots.get(region_id, {})
            latest = max(months) if months else None
            snap = months.get(latest) if latest else None
            prev = months.get(_shift_month(latest, -1)) if latest else None
            last_year = months.get(_shift_month(latest, -12)) if latest else None
            supply = snap.supply_price if snap else None
            items.append(
                RankItem(
                    region_id=region_id,
                    region_name=name,
                    year_month=latest,
                    supply_price=supply,
                    attention_price=snap.attention_price if snap else None,
                    value_price=snap.value_price if snap else None,
                    mom_pct=_pct_change(supply, prev.supply_price if prev else None),
                    yoy_pct=_pct_change(supply, last_year.supply_price if last_year else None),
                ).model_dump()
            )

        ranked = [i for i in items if i[sort_by] is not None]
        unranked = [i for i in items if i[sort_by] is None]
        ranked.sort(key=lambda i: i[sort_by], reverse=(sort_order == "desc"))
        items = ranked + unranked

        await cache.set(cache_key, json.dumps(items), ex=CACHE_TTL_ANALYTICS)

    start = (page - 1) * page_size
    return RankResponse(
        total=len(items),
        page=page,
        page_size=page_size,
        items=items[start : start + page_size],
    )


@router.get("/compare", response_model=CompareResponse)
async def price_compare(
    region_type: str = Query(..., pattern="^(city|district)$"),
    region_ids: str = Query(..., description="逗号分隔的 2~5 个区域 ID"),
    months: int = Query(12, gt=0, le=120),
    price_type: str = Query("supply_price", pattern="^(supply_price|attention_price|value_price)$"),
    db: AsyncSession = Depends(get_session),
    cache: Redis = Depends(get_cache),
):
    try:
        ids = list(dict.fromkeys(int(x) for x in region_ids.split(",") if x.strip()))
    except ValueError:
        raise HTTPException(status_code=422, detail="region_ids 必须为逗号分隔的整数")
    if not 2 <= len(ids) <= 5:
        raise HTTPException(status_code=422, detail="region_ids 数量须为 2~5 个")

    cache_key = f"api:compare:{region_type}:{','.join(map(str, ids))}:{price_type}"
    cached = await cache.get(cache_key)
    if cached:
        regions_data = json.loads(cached)
    else:
        names = await _load_regions(db, region_type, region_ids=ids)
        if any(rid not in names for rid in ids):
            raise HTTPException(status_code=404, detail="区域不存在")

        snapshots = await _load_snapshots(db, region_type, ids)
        regions_data = []
        for rid in ids:
            data = [
                {"year_month": ym, "price": getattr(snap, price_type)}
                for ym, snap in sorted(snapshots.get(rid, {}).items())
            ]
            regions_data.append({"region_id": rid, "region_name": names[rid], "data": data})

        await cache.set(cache_key, json.dumps(regions_data), ex=CACHE_TTL_ANALYTICS)

    return CompareResponse(
        price_type=price_type,
        regions=[
            CompareRegion(region_id=r["region_id"], region_name=r["region_name"], data=r["data"][-months:])
            for r in regions_data
        ],
    )


@router.get("/map/heat", response_model=MapHeatResponse)
async def map_heat(
    city_code: str = Query(...),
    region_type: str = Query("district", pattern="^district$"),
    db: AsyncSession = Depends(get_session),
    cache: Redis = Depends(get_cache),
):
    cache_key = f"api:mapheat:{city_code}:{region_type}"
    cached = await cache.get(cache_key)
    if cached:
        return json.loads(cached)

    regions = await _load_regions(db, "district", city_code=city_code)
    snapshots = await _load_snapshots(db, "district", list(regions)) if regions else {}

    data = []
    for region_id, name in regions.items():
        months = snapshots.get(region_id, {})
        latest = max(months) if months else None
        snap = months.get(latest) if latest else None
        data.append(
            MapHeatItem(
                region_id=region_id,
                region_name=name,
                price=snap.supply_price if snap else None,
            )
        )

    response = MapHeatResponse(city_code=city_code, region_type=region_type, data=data)
    await cache.set(cache_key, response.model_dump_json(), ex=CACHE_TTL_ANALYTICS)
    return response
