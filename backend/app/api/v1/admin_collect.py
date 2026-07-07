"""管理端数据采集端点：城市列表刷新、覆盖状态查询、采集任务触发。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin
from app.collector.base import SourceRegistry
from app.core.database import async_session_factory
from app.core.errors import ApiError
from app.models.city import City
from app.models.district import District
from app.models.price_snapshot import PriceSnapshot
from app.models.user import UserAccount
from app.pipeline.loaders import upsert_cities
from app.pipeline.runner import PipelineRunner
from app.schemas.admin_job import (
    AdminJobOut,
    CityCoverageListResponse,
    CityCoverageOut,
    CollectRequest,
    RefreshCitiesResponse,
)
from app.services import geo, job_runner

router = APIRouter(prefix="/admin/collect", tags=["admin"])

SOURCE_NAME = "creprice"


@router.post("/cities/refresh", response_model=RefreshCitiesResponse)
async def refresh_cities(
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """从数据源刷新全国城市列表（一次 HTTP 请求，同步执行）。"""
    source = SourceRegistry.get(SOURCE_NAME)
    cities = await asyncio.to_thread(source.fetch_cities)
    await upsert_cities(db, cities)
    await db.commit()
    total = (await db.execute(select(func.count(City.id)))).scalar_one()
    return RefreshCitiesResponse(total=total)


@router.get("/cities", response_model=CityCoverageListResponse)
async def list_city_coverage(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    keyword: str | None = Query(None, max_length=50),
    province: str | None = Query(None, max_length=50),
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """城市列表 + 数据覆盖状态（区县数/最新快照月份/有无地图）。"""
    dist_count = (
        select(District.city_id, func.count(District.id).label("cnt"))
        .group_by(District.city_id)
        .subquery()
    )
    latest_month = (
        select(
            PriceSnapshot.region_id,
            func.max(PriceSnapshot.year_month).label("latest"),
        )
        .where(PriceSnapshot.region_type == "city")
        .group_by(PriceSnapshot.region_id)
        .subquery()
    )

    conditions = []
    if keyword:
        pattern = f"%{keyword}%"
        conditions.append(or_(City.name.ilike(pattern), City.code.ilike(pattern)))
    if province:
        conditions.append(City.province == province)

    total = (
        await db.execute(select(func.count(City.id)).where(*conditions))
    ).scalar_one()

    rows = (
        await db.execute(
            select(
                City,
                func.coalesce(dist_count.c.cnt, 0).label("district_count"),
                latest_month.c.latest,
            )
            .outerjoin(dist_count, dist_count.c.city_id == City.id)
            .outerjoin(latest_month, latest_month.c.region_id == City.id)
            .where(*conditions)
            .order_by(City.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    geo_codes = geo.list_available()
    items = [
        CityCoverageOut(
            id=city.id,
            name=city.name,
            code=city.code,
            province=city.province,
            district_count=cnt,
            latest_month=latest,
            has_geo=city.code in geo_codes,
        )
        for city, cnt, latest in rows
    ]
    return CityCoverageListResponse(total=total, page=page, page_size=page_size, items=items)


async def _resolve_collect_targets(db: AsyncSession, payload: CollectRequest) -> list[str]:
    """解析采集目标城市 code 列表。"""
    if payload.all:
        rows = await db.execute(select(City.code).order_by(City.id))
        return list(rows.scalars())
    if payload.all_missing:
        # 无任何城市级快照的城市视为缺数据
        covered = (
            select(PriceSnapshot.region_id)
            .where(PriceSnapshot.region_type == "city")
            .distinct()
        )
        rows = await db.execute(
            select(City.code).where(City.id.not_in(covered)).order_by(City.id)
        )
        return list(rows.scalars())

    if not payload.city_codes:
        raise ApiError(422, "city_codes 不能为空（或指定 all / all_missing）", "VALIDATION_ERROR")
    existing = set(
        (
            await db.execute(select(City.code).where(City.code.in_(payload.city_codes)))
        ).scalars()
    )
    unknown = [c for c in payload.city_codes if c not in existing]
    if unknown:
        raise ApiError(422, f"未知城市 code: {', '.join(unknown[:10])}", "VALIDATION_ERROR")
    return payload.city_codes


async def _run_collect(job_id: int, city_codes: list[str]) -> None:
    """采集任务体：逐城市执行完整 pipeline，失败不中断，摘要写入 result。"""
    runner = PipelineRunner(async_session_factory)
    results: list[dict] = []
    for i, code in enumerate(city_codes, start=1):
        try:
            stats = await runner.run(SOURCE_NAME, code)
            results.append(
                {
                    "city": code,
                    "ok": True,
                    "snapshots": stats["snapshots"],
                    "distributions": stats["distributions"],
                }
            )
        except Exception as exc:
            results.append({"city": code, "ok": False, "error": str(exc)[:500]})
        await job_runner.report_progress(job_id, i, result=results)

    if results and not any(r["ok"] for r in results):
        raise RuntimeError(f"全部 {len(results)} 个城市采集失败")


@router.post("", response_model=AdminJobOut, status_code=202)
async def submit_collect(
    payload: CollectRequest,
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """创建采集后台任务（同类任务互斥，进行中重复提交返回 409）。"""
    city_codes = await _resolve_collect_targets(db, payload)
    if not city_codes:
        raise ApiError(422, "没有需要采集的城市", "VALIDATION_ERROR")

    job = await job_runner.submit(
        "collect",
        {"city_codes": city_codes},
        lambda job_id: _run_collect(job_id, city_codes),
        progress_total=len(city_codes),
    )
    return job
