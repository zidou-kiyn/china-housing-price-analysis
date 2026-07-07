"""GeoJSON 端点：管理端地图爬取任务 + 登录用户地图读取。"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin, require_user
from app.core.database import async_session_factory
from app.core.errors import ApiError
from app.models.city import City
from app.models.district import District
from app.models.user import UserAccount
from app.schemas.admin_job import AdminJobOut, GeoFetchRequest
from app.services import geo, job_runner

admin_router = APIRouter(prefix="/admin/geo", tags=["admin"])
public_router = APIRouter(prefix="/geo", tags=["geo"])


async def _resolve_geo_targets(db: AsyncSession, payload: GeoFetchRequest) -> list[str]:
    if payload.all_missing:
        # 已采集（有区县）但还没有地图文件的城市
        collected = select(District.city_id).distinct()
        rows = await db.execute(
            select(City.code).where(City.id.in_(collected)).order_by(City.id)
        )
        available = geo.list_available()
        return [c for c in rows.scalars() if c not in available]

    if not payload.city_codes:
        raise ApiError(422, "city_codes 不能为空（或指定 all_missing）", "VALIDATION_ERROR")
    existing = set(
        (
            await db.execute(select(City.code).where(City.code.in_(payload.city_codes)))
        ).scalars()
    )
    unknown = [c for c in payload.city_codes if c not in existing]
    if unknown:
        raise ApiError(422, f"未知城市 code: {', '.join(unknown[:10])}", "VALIDATION_ERROR")
    return payload.city_codes


async def _run_geo_fetch(job_id: int, city_codes: list[str]) -> None:
    """地图爬取任务体：必要时先批量回填 adcode，再逐城市下载落盘。"""
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=30) as client:
        async with async_session_factory() as session:
            cities = {
                c.code: c
                for c in (
                    await session.execute(select(City).where(City.code.in_(city_codes)))
                ).scalars()
            }
            if any(cities[c].adcode is None for c in city_codes if c in cities):
                await geo.backfill_adcodes(session, client)
                # 回填后重读，拿到最新 adcode
                cities = {
                    c.code: c
                    for c in (
                        await session.execute(
                            select(City).where(City.code.in_(city_codes))
                        )
                    ).scalars()
                }

        for i, code in enumerate(city_codes, start=1):
            city = cities.get(code)
            try:
                if city is None:
                    raise ValueError(f"city 表中无代码 {code}")
                summary = await geo.fetch_city_geo(client, city)
                results.append({"city": code, "ok": True, **summary})
            except Exception as exc:
                results.append({"city": code, "ok": False, "error": str(exc)[:500]})
            await job_runner.report_progress(job_id, i, result=results)
            await asyncio.sleep(geo.REQUEST_INTERVAL)

    if results and not any(r["ok"] for r in results):
        raise RuntimeError(f"全部 {len(results)} 个城市地图爬取失败")


@admin_router.post("/fetch", response_model=AdminJobOut, status_code=202)
async def submit_geo_fetch(
    payload: GeoFetchRequest,
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """创建地图爬取后台任务（同类任务互斥）。"""
    city_codes = await _resolve_geo_targets(db, payload)
    if not city_codes:
        raise ApiError(422, "没有需要爬取地图的城市", "VALIDATION_ERROR")

    job = await job_runner.submit(
        "geo_fetch",
        {"city_codes": city_codes},
        lambda job_id: _run_geo_fetch(job_id, city_codes),
        progress_total=len(city_codes),
    )
    return job


@public_router.get("/{city_code}")
async def get_city_geo(
    city_code: str,
    _user: UserAccount = Depends(require_user),
):
    """返回城市区县边界 GeoJSON（登录可见）。"""
    path = geo.geo_path(city_code)
    if not path.is_file():
        raise ApiError(404, f"城市 {city_code} 暂无地图数据", "GEO_NOT_FOUND")
    return FileResponse(path, media_type="application/json")
