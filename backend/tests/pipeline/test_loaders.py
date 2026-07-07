"""Loader upsert 集成测试：使用真实 PostgreSQL 验证 INSERT ON CONFLICT 逻辑。"""

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.collector.base import CityInfo, DistrictInfo
from app.core.config import settings
from app.models.city import City
from app.models.crawl_job import CrawlJob
from app.models.crawl_log import CrawlLog
from app.models.district import District
from app.models.price_distribution import PriceDistribution
from app.models.price_snapshot import PriceSnapshot
from app.pipeline.loaders import (
    create_crawl_job,
    create_crawl_log,
    finish_crawl_job,
    upsert_cities,
    upsert_districts,
    upsert_price_distributions,
    upsert_price_snapshots,
)

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="module")]


@pytest.fixture(scope="module")
def engine():
    return create_async_engine(settings.database_url, echo=False)


@pytest.fixture(scope="module")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(loop_scope="module")
async def session(session_factory):
    async with session_factory() as s:
        async with s.begin():
            yield s


# ── upsert_cities ──────────────────────────────────────────────────

class TestUpsertCities:
    async def test_insert_new_cities(self, session):
        cities = [
            CityInfo(name="测试市A", code="test_a"),
            CityInfo(name="测试市B", code="test_b"),
        ]
        mapping = await upsert_cities(session, cities)
        assert "test_a" in mapping
        assert "test_b" in mapping
        assert isinstance(mapping["test_a"], int)

    async def test_upsert_updates_name(self, session):
        await upsert_cities(session, [CityInfo(name="旧名", code="test_upsert_city")])
        mapping = await upsert_cities(session, [CityInfo(name="新名", code="test_upsert_city")])

        result = await session.execute(
            select(City).where(City.code == "test_upsert_city")
        )
        city = result.scalar_one()
        assert city.name == "新名"
        assert mapping["test_upsert_city"] == city.id

    async def test_empty_list(self, session):
        mapping = await upsert_cities(session, [])
        assert isinstance(mapping, dict)


# ── upsert_districts ───────────────────────────────────────────────

class TestUpsertDistricts:
    async def test_insert_districts(self, session):
        city_map = await upsert_cities(session, [CityInfo(name="区县测试市", code="dist_test_city")])
        districts = [
            DistrictInfo(name="区一", code="dist_1", city_code="dist_test_city"),
            DistrictInfo(name="区二", code="dist_2", city_code="dist_test_city"),
        ]
        dist_map = await upsert_districts(session, districts, city_map)
        assert "dist_1" in dist_map
        assert "dist_2" in dist_map

    async def test_skips_unknown_city(self, session):
        districts = [
            DistrictInfo(name="孤区", code="orphan_dist", city_code="nonexistent_city"),
        ]
        dist_map = await upsert_districts(session, districts, {})
        assert "orphan_dist" not in dist_map

    async def test_upsert_updates_district_name(self, session):
        city_map = await upsert_cities(session, [CityInfo(name="更新区县市", code="upd_dist_city")])
        await upsert_districts(
            session,
            [DistrictInfo(name="旧区名", code="upd_dist", city_code="upd_dist_city")],
            city_map,
        )
        await upsert_districts(
            session,
            [DistrictInfo(name="新区名", code="upd_dist", city_code="upd_dist_city")],
            city_map,
        )

        result = await session.execute(select(District).where(District.code == "upd_dist"))
        assert result.scalar_one().name == "新区名"


# ── upsert_price_snapshots ─────────────────────────────────────────

class TestUpsertPriceSnapshots:
    async def test_insert_snapshots(self, session):
        city_map = await upsert_cities(session, [CityInfo(name="快照市", code="snap_city")])
        city_id = city_map["snap_city"]

        records = [
            {"year_month": "2025-01", "supply_price": 9000, "attention_price": 8500, "value_price": 9200, "sample_count": 100},
            {"year_month": "2025-02", "supply_price": 9100, "attention_price": 8600, "value_price": 9300, "sample_count": 110},
        ]
        count = await upsert_price_snapshots(session, records, "city", city_id)
        assert count == 2

    async def test_upsert_updates_price(self, session):
        city_map = await upsert_cities(session, [CityInfo(name="更新快照市", code="upd_snap_city")])
        city_id = city_map["upd_snap_city"]

        records = [{"year_month": "2025-03", "supply_price": 8000}]
        await upsert_price_snapshots(session, records, "city", city_id)

        updated = [{"year_month": "2025-03", "supply_price": 9999}]
        await upsert_price_snapshots(session, updated, "city", city_id)

        result = await session.execute(
            select(PriceSnapshot).where(
                PriceSnapshot.region_type == "city",
                PriceSnapshot.region_id == city_id,
                PriceSnapshot.year_month == "2025-03",
            )
        )
        assert result.scalar_one().supply_price == 9999

    async def test_idempotent_count(self, session):
        city_map = await upsert_cities(session, [CityInfo(name="幂等市", code="idem_city")])
        city_id = city_map["idem_city"]

        records = [{"year_month": "2025-04", "supply_price": 7000}]
        await upsert_price_snapshots(session, records, "city", city_id)
        await upsert_price_snapshots(session, records, "city", city_id)

        result = await session.execute(
            select(func.count()).select_from(PriceSnapshot).where(
                PriceSnapshot.region_type == "city",
                PriceSnapshot.region_id == city_id,
            )
        )
        assert result.scalar() == 1

    async def test_empty_records(self, session):
        assert await upsert_price_snapshots(session, [], "city", 999) == 0


# ── upsert_price_distributions ─────────────────────────────────────

class TestUpsertPriceDistributions:
    async def test_insert_distributions(self, session):
        city_map = await upsert_cities(session, [CityInfo(name="分布市", code="dist_price_city")])
        city_id = city_map["dist_price_city"]

        records = [
            {"year_month": "2025-07", "price_range_low": 6000, "price_range_high": 7000, "percentage": 12.5, "count": 50},
            {"year_month": "2025-07", "price_range_low": 7000, "price_range_high": 8000, "percentage": 25.0, "count": 100},
        ]
        count = await upsert_price_distributions(session, records, "city", city_id)
        assert count == 2

    async def test_upsert_updates_percentage(self, session):
        city_map = await upsert_cities(session, [CityInfo(name="更新分布市", code="upd_dist_price_city")])
        city_id = city_map["upd_dist_price_city"]

        records = [{"year_month": "2025-07", "price_range_low": 5000, "price_range_high": 6000, "percentage": 10.0}]
        await upsert_price_distributions(session, records, "city", city_id)

        updated = [{"year_month": "2025-07", "price_range_low": 5000, "price_range_high": 6000, "percentage": 20.0}]
        await upsert_price_distributions(session, updated, "city", city_id)

        result = await session.execute(
            select(PriceDistribution).where(
                PriceDistribution.region_type == "city",
                PriceDistribution.region_id == city_id,
                PriceDistribution.price_range_low == 5000,
            )
        )
        assert float(result.scalar_one().percentage) == 20.0

    async def test_empty_records(self, session):
        assert await upsert_price_distributions(session, [], "city", 999) == 0


# ── crawl_job / crawl_log ──────────────────────────────────────────

class TestCrawlJobLog:
    async def test_create_and_finish_job(self, session):
        job = await create_crawl_job(session, "test_source", "test_city")
        assert job.status == "running"
        assert job.started_at is not None
        assert job.id is not None

        await finish_crawl_job(session, job, success=True)
        assert job.status == "completed"
        assert job.finished_at is not None

    async def test_failed_job(self, session):
        job = await create_crawl_job(session, "test_source", "fail_city")
        await finish_crawl_job(session, job, success=False)
        assert job.status == "failed"

    async def test_create_crawl_log(self, session):
        job = await create_crawl_job(session, "test_source", "log_city")
        log = await create_crawl_log(
            session,
            job_id=job.id,
            url="https://example.com/api",
            success=True,
            status_code=200,
            record_count=42,
            elapsed_ms=150,
        )
        assert log.id is not None
        assert log.job_id == job.id
        assert log.record_count == 42

    async def test_error_log(self, session):
        job = await create_crawl_job(session, "test_source", "err_city")
        log = await create_crawl_log(
            session,
            job_id=job.id,
            url="https://example.com/fail",
            success=False,
            error_message="Connection timeout",
        )
        assert log.success is False
        assert log.error_message == "Connection timeout"
