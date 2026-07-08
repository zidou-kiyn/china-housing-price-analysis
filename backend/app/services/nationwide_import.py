"""全国城市年度房价批量导入：58/anjuke 年度数据集 → 城市级 price_snapshot。

与 PipelineRunner 的按-code 逐城管线不同，本服务一次下载全国 CSV，按**城市名**
匹配 city 表后批量 upsert（数据集无 creprice code，阻抗不匹配，见任务 design.md）。
未匹配城市（县级市/自治州/香港等）跳过并记录，不新建脏城市行。
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collector.sources.listing_annual import (
    SOURCES,
    download_csv,
    parse_annual_csv,
)
from app.core.cache import invalidate_api_caches, redis_client
from app.models.city import City
from app.pipeline.loaders import upsert_price_snapshots

logger = logging.getLogger(__name__)


async def import_annual(session: AsyncSession, source_key: str = "58") -> dict:
    """导入指定源的全国年度房价到城市级快照，返回覆盖统计。

    年度值按约定落 ``year_month=f"{year}-12"``；挂牌均价写 supply_price、
    sample_count 留空。幂等：upsert on (region_type, region_id, year_month)，
    重跑覆盖同值不产生重复。
    """
    if source_key not in SOURCES:
        raise ValueError(f"未知年度房价源: {source_key}（可选: {sorted(SOURCES)}）")
    source_tag = SOURCES[source_key][1]

    csv_path = await asyncio.to_thread(download_csv, source_key)
    rows = parse_annual_csv(csv_path.read_text(encoding="utf-8"))

    name_to_id: dict[str, int] = dict(
        (await session.execute(select(City.name, City.id))).all()
    )

    # 按城市名分组；同城同年重复行以后出现者为准（防御 multi-row upsert 冲突）
    by_city: dict[str, dict[int, int]] = {}
    for row in rows:
        by_city.setdefault(row["city"], {})[row["year"]] = row["price"]

    matched = 0
    snapshots = 0
    skipped: list[str] = []
    for city_name in sorted(by_city):
        city_id = name_to_id.get(city_name)
        if city_id is None:
            skipped.append(city_name)
            continue
        year_prices = by_city[city_name]
        records = [
            {
                "year_month": f"{year}-12",
                "supply_price": year_prices[year],
                "sample_count": None,
            }
            for year in sorted(year_prices)
        ]
        snapshots += await upsert_price_snapshots(
            session, records, "city", city_id, source=source_tag
        )
        matched += 1

    await session.commit()

    if skipped:
        logger.info(
            "年度导入 %s：%d 城名未匹配跳过: %s",
            source_key, len(skipped), "、".join(skipped),
        )

    try:
        # 批量导入涉及全国城市，按-code 参数传 "*" 使 per-city 缓存模式整体通配
        deleted = await invalidate_api_caches(redis_client, "*")
        if deleted:
            logger.info("已清除 %d 个缓存 key", deleted)
    except Exception:
        logger.warning("Redis 缓存清除失败，不影响入库结果", exc_info=True)

    return {
        "source": source_tag,
        "matched": matched,
        "skipped": skipped,
        "snapshots": snapshots,
    }
