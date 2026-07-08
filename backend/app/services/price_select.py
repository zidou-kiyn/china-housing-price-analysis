"""价格快照读取层选择器。

creprice-first 方针（2026-07-08）后读取层不再跨源合并：视图按单一 source 直读
（select_snapshots_for_source），各源硬隔离；ML 训练集构建器仍按源分组取全序列
（select_source_snapshots）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_snapshot import PriceSnapshot


async def select_snapshots_for_source(
    session: AsyncSession,
    source: str,
    region_type: str | None = None,
    region_ids: list[int] | None = None,
) -> list[PriceSnapshot]:
    """单源直读：`WHERE source == :source`，区域/月份升序，不做任何跨源合并。"""
    stmt = (
        select(PriceSnapshot)
        .where(PriceSnapshot.source == source)
        .order_by(
            PriceSnapshot.region_type,
            PriceSnapshot.region_id,
            PriceSnapshot.year_month,
        )
    )
    if region_type:
        stmt = stmt.where(PriceSnapshot.region_type == region_type)
    if region_ids:
        stmt = stmt.where(PriceSnapshot.region_id.in_(region_ids))
    result = await session.execute(stmt)
    return list(result.scalars())


async def select_source_snapshots(
    session: AsyncSession,
    region_type: str | None = None,
    region_ids: list[int] | None = None,
) -> dict[str, list[PriceSnapshot]]:
    """按源分组返回全部快照行（不做同月合并），每源内按区域、月份升序。"""
    stmt = select(PriceSnapshot).order_by(
        PriceSnapshot.source,
        PriceSnapshot.region_type,
        PriceSnapshot.region_id,
        PriceSnapshot.year_month,
    )
    if region_type:
        stmt = stmt.where(PriceSnapshot.region_type == region_type)
    if region_ids:
        stmt = stmt.where(PriceSnapshot.region_id.in_(region_ids))
    result = await session.execute(stmt)
    by_source: dict[str, list[PriceSnapshot]] = {}
    for snap in result.scalars():
        by_source.setdefault(snap.source, []).append(snap)
    return by_source
