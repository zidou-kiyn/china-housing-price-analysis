"""数据库 upsert 操作：异步，基于 PostgreSQL INSERT ON CONFLICT。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collector.base import CityInfo, DistrictInfo
from app.models.city import City
from app.models.crawl_job import CrawlJob
from app.models.crawl_log import CrawlLog
from app.models.district import District
from app.models.price_distribution import PriceDistribution
from app.models.price_snapshot import PriceSnapshot


async def upsert_cities(
    session: AsyncSession, cities: list[CityInfo]
) -> dict[str, int]:
    """upsert 城市列表，返回 code → id 映射。"""
    for city in cities:
        stmt = insert(City).values(
            name=city.name, code=city.code, province=city.province
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["code"],
            # province 仅在来源有值时覆盖，避免旧数据被 None 清空
            set_={
                "name": stmt.excluded.name,
                "province": func.coalesce(stmt.excluded.province, City.province),
            },
        )
        await session.execute(stmt)
    await session.flush()

    result = await session.execute(select(City.code, City.id))
    return dict(result.all())


async def upsert_districts(
    session: AsyncSession,
    districts: list[DistrictInfo],
    city_code_to_id: dict[str, int],
) -> dict[str, int]:
    """upsert 区县列表，返回 dist_code → id 映射（仅限当前城市的区县）。"""
    for dist in districts:
        city_id = city_code_to_id.get(dist.city_code)
        if city_id is None:
            continue
        stmt = insert(District).values(
            name=dist.name, code=dist.code, city_id=city_id
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["code"],
            set_={"name": stmt.excluded.name, "city_id": stmt.excluded.city_id},
        )
        await session.execute(stmt)
    await session.flush()

    dist_codes = [d.code for d in districts]
    result = await session.execute(
        select(District.code, District.id).where(District.code.in_(dist_codes))
    )
    return dict(result.all())


async def upsert_price_snapshots(
    session: AsyncSession,
    records: list[dict],
    region_type: str,
    region_id: int,
    source: str | None = None,
) -> int:
    """批量 upsert 均价快照，返回入库行数。source 记录该行最后写入的数据源（溯源注记）。"""
    if not records:
        return 0
    rows = [
        {
            "region_type": region_type,
            "region_id": region_id,
            "year_month": r["year_month"],
            "supply_price": r.get("supply_price"),
            "attention_price": r.get("attention_price"),
            "value_price": r.get("value_price"),
            "sample_count": r.get("sample_count"),
            "source": source,
        }
        for r in records
    ]
    stmt = insert(PriceSnapshot).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_price_snapshot_region_month",
        set_={
            "supply_price": stmt.excluded.supply_price,
            "attention_price": stmt.excluded.attention_price,
            "value_price": stmt.excluded.value_price,
            "sample_count": stmt.excluded.sample_count,
            "source": stmt.excluded.source,
        },
    )
    result = await session.execute(stmt)
    return result.rowcount


async def upsert_price_distributions(
    session: AsyncSession,
    records: list[dict],
    region_type: str,
    region_id: int,
) -> int:
    """批量 upsert 价格分布，返回入库行数。"""
    if not records:
        return 0
    rows = [
        {
            "region_type": region_type,
            "region_id": region_id,
            "year_month": r["year_month"],
            "price_range_low": r["price_range_low"],
            "price_range_high": r["price_range_high"],
            "percentage": Decimal(str(r["percentage"])) if r.get("percentage") is not None else None,
            "count": r.get("count"),
        }
        for r in records
    ]
    stmt = insert(PriceDistribution).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_price_distribution_region_range",
        set_={
            "price_range_high": stmt.excluded.price_range_high,
            "percentage": stmt.excluded.percentage,
            "count": stmt.excluded.count,
        },
    )
    result = await session.execute(stmt)
    return result.rowcount


async def create_crawl_job(
    session: AsyncSession, source: str, city_code: str, job_type: str = "full"
) -> CrawlJob:
    """创建采集任务记录。"""
    job = CrawlJob(
        source=source,
        city_code=city_code,
        job_type=job_type,
        status="running",
        started_at=datetime.now(),
    )
    session.add(job)
    await session.flush()
    return job


async def finish_crawl_job(
    session: AsyncSession, job: CrawlJob, success: bool
) -> None:
    """更新采集任务状态。"""
    job.status = "completed" if success else "failed"
    job.finished_at = datetime.now()
    await session.flush()


async def create_crawl_log(
    session: AsyncSession,
    job_id: int,
    url: str,
    success: bool,
    status_code: int | None = None,
    error_message: str | None = None,
    raw_path: str | None = None,
    record_count: int = 0,
    elapsed_ms: int | None = None,
) -> CrawlLog:
    """记录单次请求日志。"""
    log = CrawlLog(
        job_id=job_id,
        url=url,
        status_code=status_code,
        success=success,
        error_message=error_message,
        raw_path=raw_path,
        record_count=record_count,
        elapsed_ms=elapsed_ms,
    )
    session.add(log)
    await session.flush()
    return log
