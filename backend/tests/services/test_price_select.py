"""price_select 合并选择单测：多源同月按优先级取一行（真实 DB，自清理）。"""

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.core.database import async_session_factory
from app.models.city import City
from app.models.price_snapshot import PriceSnapshot
from app.pipeline.loaders import upsert_price_snapshots
from app.services.price_select import select_merged_snapshots, select_source_snapshots

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def multi_source_city():
    """seed 一个城市：2024-12 双源共存 + 2020-12 仅年度源 + 2025-01 仅月度源。"""
    async with async_session_factory() as s:
        city = City(name="合并选择市", code="t_merge", province="单测省")
        s.add(city)
        await s.commit()
        city_id = city.id

        await upsert_price_snapshots(
            s, [{"year_month": "2024-12", "supply_price": 9000},
                {"year_month": "2025-01", "supply_price": 9100}],
            "city", city_id, source="creprice",
        )
        await upsert_price_snapshots(
            s, [{"year_month": "2020-12", "supply_price": 11000},
                {"year_month": "2024-12", "supply_price": 13000}],
            "city", city_id, source="listing_annual_58",
        )
        await s.commit()
    yield city_id
    async with async_session_factory() as s:
        await s.execute(
            delete(PriceSnapshot).where(
                PriceSnapshot.region_type == "city",
                PriceSnapshot.region_id == city_id,
            )
        )
        await s.execute(delete(City).where(City.id == city_id))
        await s.commit()


async def test_merged_prefers_monthly_source(multi_source_city):
    async with async_session_factory() as s:
        snaps = await select_merged_snapshots(s, "city", [multi_source_city])

    assert [(x.year_month, x.supply_price, x.source) for x in snaps] == [
        ("2020-12", 11000, "listing_annual_58"),  # 仅年度源 → 用年度值
        ("2024-12", 9000, "creprice"),  # 双源共存 → 月度源优先
        ("2025-01", 9100, "creprice"),
    ]


async def test_source_snapshots_grouped_not_merged(multi_source_city):
    """分源取数：各源完整序列独立返回，同月双源共存不合并。"""
    async with async_session_factory() as s:
        by_source = await select_source_snapshots(s, "city", [multi_source_city])

    assert set(by_source) == {"creprice", "listing_annual_58"}
    assert [(x.year_month, x.supply_price) for x in by_source["creprice"]] == [
        ("2024-12", 9000),
        ("2025-01", 9100),
    ]
    assert [(x.year_month, x.supply_price) for x in by_source["listing_annual_58"]] == [
        ("2020-12", 11000),
        ("2024-12", 13000),
    ]


async def test_merged_scopes_by_region(multi_source_city):
    async with async_session_factory() as s:
        snaps = await select_merged_snapshots(s, "city", [multi_source_city])
        assert all(x.region_id == multi_source_city for x in snaps)
        # 不传 region_ids 时包含其他区域，仍无同区域同月重复
        all_snaps = await select_merged_snapshots(s, "city")
        keys = [(x.region_id, x.year_month) for x in all_snaps]
        assert len(keys) == len(set(keys))