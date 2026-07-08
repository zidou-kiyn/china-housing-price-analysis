"""多源快照的读取层选择器。

存储层各源独立后，同一 (region, month) 可能有多行。creprice-first 方针
（2026-07-08）后**读取层不再跨源合并**：视图按单一 `source` 直读
（`select_snapshots_for_source`），各源硬隔离；ML 训练集构建器仍按源分组取全序列
（`select_source_snapshots`），校准/扩充需要各源完整序列。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_index_snapshot import PriceIndexSnapshot
from app.models.price_snapshot import PriceSnapshot


async def select_snapshots_for_source(
    session: AsyncSession,
    source: str,
    region_type: str | None = None,
    region_ids: list[int] | None = None,
) -> list[PriceSnapshot]:
    """单源直读：`WHERE source == :source`，区域/月份升序，不做任何跨源合并。

    读取层源硬隔离的唯一取数入口（默认走势/排行/对比/地图/概览）。年度源行原样
    返回（year_month=YYYY-12），不做月度换算——单源口径一致由调用方按 source 标注。
    """
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
    """按源分组返回全部快照行（不做同月合并），每源内按区域、月份升序。

    供 ML 训练集构建器分源处理（口径校准/年度扩充需要各源完整序列，
    单值合并会丢掉重叠期的双口径对）。
    """
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


async def select_index_snapshots(
    session: AsyncSession,
    region_type: str | None = None,
    region_ids: list[int] | None = None,
    dwelling_type: str = "second",
    base_type: str = "mom",
) -> list[PriceIndexSnapshot]:
    """按口径取房价指数行，区域、月份升序。

    默认二手房环比（与年度挂牌均价口径最接近）——供 ML 年度序列月度赋形
    与跨源审计取数。指数不进 SOURCE_PRIORITY 合并（不是 ¥/㎡ 快照源）。
    """
    stmt = (
        select(PriceIndexSnapshot)
        .where(
            PriceIndexSnapshot.dwelling_type == dwelling_type,
            PriceIndexSnapshot.base_type == base_type,
        )
        .order_by(
            PriceIndexSnapshot.region_type,
            PriceIndexSnapshot.region_id,
            PriceIndexSnapshot.year_month,
        )
    )
    if region_type:
        stmt = stmt.where(PriceIndexSnapshot.region_type == region_type)
    if region_ids:
        stmt = stmt.where(PriceIndexSnapshot.region_id.in_(region_ids))
    result = await session.execute(stmt)
    return list(result.scalars())
