"""多源快照的合并选择（读取层唯一入口）。

存储层各源独立后，同一 (region, month) 可能有多行；需要"每月单值"的读取方
（默认走势/排行/对比/预测取数）统一走这里：按 source_policy 优先级每月取一行
（月度成交/评估 > 年度挂牌），来源保留在行的 source 字段供口径标注。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.source_policy import priority_case
from app.models.price_index_snapshot import PriceIndexSnapshot
from app.models.price_snapshot import PriceSnapshot


async def select_merged_snapshots(
    session: AsyncSession,
    region_type: str | None = None,
    region_ids: list[int] | None = None,
) -> list[PriceSnapshot]:
    """每 (region_type, region_id, year_month) 按源优先级取一行，按月升序返回。"""
    stmt = (
        select(PriceSnapshot)
        .distinct(
            PriceSnapshot.region_type,
            PriceSnapshot.region_id,
            PriceSnapshot.year_month,
        )
        .order_by(
            PriceSnapshot.region_type,
            PriceSnapshot.region_id,
            PriceSnapshot.year_month,
            priority_case(),
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
