"""管理端数据采集端点：城市列表刷新、覆盖状态查询、采集任务触发。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin
from app.collector.base import SourceRegistry
from app.collector.sources.listing_annual import SOURCES as ANNUAL_SOURCES
from app.core.database import async_session_factory
from app.core.errors import ApiError
from app.models.city import City
from app.models.district import District
from app.models.price_snapshot import PriceSnapshot
from app.models.user import UserAccount
from app.pipeline.loaders import upsert_cities
from app.schemas.admin_job import (
    AdminJobOut,
    AnnualImportRequest,
    AnnualImportResult,
    CityCoverageListResponse,
    CityCoverageOut,
    CollectRequest,
    CollectSourceOut,
    CollectSourcesResponse,
    CollectSourceUpdate,
    RefreshCitiesResponse,
)
from app.services import geo, index_import, job_runner, nationwide_import
from app.services.app_settings import get_collect_source, set_collect_source
from app.services.collect_tasks import run_collect

router = APIRouter(prefix="/admin/collect", tags=["admin"])


def _resolve_source(name: str) -> str:
    """校验源名已注册，否则 422。返回原名，便于链式使用。"""
    if name not in SourceRegistry.names():
        raise ApiError(422, f"未知数据源: {name}", "VALIDATION_ERROR")
    return name


async def _build_sources_response(db: AsyncSession) -> CollectSourcesResponse:
    """列出已注册源的能力 + 当前默认源（读类属性，不实例化源）。"""
    current = await get_collect_source(db)
    items = []
    for name in SourceRegistry.names():
        cls = SourceRegistry.get_class(name)
        items.append(
            CollectSourceOut(
                name=name,
                capabilities=sorted(cls.capabilities),
                price_unit=cls.price_unit,
            )
        )
    return CollectSourcesResponse(current=current, items=items)


@router.get("/sources", response_model=CollectSourcesResponse)
async def list_sources(
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """列出可用采集源（含能力、均价语义）与当前默认源。"""
    return await _build_sources_response(db)


@router.put("/source", response_model=CollectSourcesResponse)
async def set_source(
    payload: CollectSourceUpdate,
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """设置当前默认采集源（前端"数据源切换"落点）；未注册源 422。"""
    _resolve_source(payload.source)
    await set_collect_source(db, payload.source)
    return await _build_sources_response(db)


@router.post("/cities/refresh", response_model=RefreshCitiesResponse)
async def refresh_cities(
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """从当前默认数据源刷新全国城市列表（一次 HTTP 请求，同步执行）。"""
    source_name = _resolve_source(await get_collect_source(db))
    source = SourceRegistry.get(source_name)
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


@router.post("/import-annual", response_model=AnnualImportResult)
async def import_annual_prices(
    payload: AnnualImportRequest,
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """导入 58/anjuke 全国城市年度房价（同步执行，~330 城一次 bulk）；未知源 422。"""
    if payload.source not in ANNUAL_SOURCES:
        raise ApiError(422, f"未知年度房价源: {payload.source}", "VALIDATION_ERROR")
    stats = await nationwide_import.import_annual(db, payload.source)
    return AnnualImportResult(
        source=stats["source"],
        matched=stats["matched"],
        skipped_count=len(stats["skipped"]),
        skipped_cities=stats["skipped"],
        snapshots=stats["snapshots"],
        rejected=stats.get("rejected", 0),
        flagged=stats.get("flagged", 0),
    )


async def _run_import_index(job_id: int) -> None:
    """指数导入任务体：下载/解析/对齐/upsert 在独立 session，统计写入 job result。

    下载或解析失败直接抛出 → job 显式 failed（不静默空导入）。
    """
    async with async_session_factory() as db:
        stats = await index_import.import_index(db)
    await job_runner.report_progress(job_id, 1, total=1, result=[{"ok": True, **stats}])


@router.post("/import-index", response_model=AdminJobOut, status_code=202)
async def import_index_prices(
    _admin: UserAccount = Depends(require_admin),
):
    """导入 NBS 70 城月度房价指数（GitHub 直链 CSV，异步 job）。

    约 1.3 万 CSV 行 × 新建/二手两口径 ≈ 2.6 万行 upsert，走后台任务；
    导入/跳过统计在 job result[0]。
    """
    return await job_runner.submit(
        "import_index",
        {"source": index_import.INDEX_SOURCE_TAG},
        _run_import_index,
        progress_total=1,
    )


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


async def _run_collect(job_id: int, city_codes: list[str], source_name: str) -> None:
    """手动采集任务体：逐城市执行完整 pipeline，失败不中断，摘要写入 result。

    共用循环抽到 services.collect_tasks.run_collect；手动路径不加节流/熔断
    （定时路径才需要，见 collect_scheduler），保持既有行为与 job result 结构。
    """
    summary = await run_collect(job_id, city_codes, source_name)
    results = summary["results"]
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

    # 源解析优先级：请求显式 source > KV 当前默认源 > 常量兜底
    source_name = _resolve_source(payload.source or await get_collect_source(db))

    job = await job_runner.submit(
        "collect",
        {"city_codes": city_codes, "source": source_name},
        lambda job_id: _run_collect(job_id, city_codes, source_name),
        progress_total=len(city_codes),
    )
    return job
