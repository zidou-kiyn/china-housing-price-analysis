"""Loader upsert 集成测试：使用真实 PostgreSQL 验证 INSERT ON CONFLICT 逻辑。"""

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
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

# 本模块写入真实 DB 的全部测试城市代码；新增用例的城市代码必须登记在这里，
# 否则会泄漏进 dev 库并出现在前端排行榜（曾发生：快照市/幂等市上榜）
TEST_CITY_CODES = [
    "test_a", "test_b", "test_upsert_city", "dist_test_city", "upd_dist_city",
    "snap_city", "upd_snap_city", "idem_city", "dist_price_city", "upd_dist_price_city",
    "coex_city",
]
TEST_JOB_SOURCE = "test_source"


async def _purge_test_rows(session_factory) -> None:
    async with session_factory() as s:
        async with s.begin():
            city_ids = (
                (await s.execute(select(City.id).where(City.code.in_(TEST_CITY_CODES))))
                .scalars().all()
            )
            if city_ids:
                dist_ids = (
                    (await s.execute(select(District.id).where(District.city_id.in_(city_ids))))
                    .scalars().all()
                )
                for region_type, ids in (("city", city_ids), ("district", dist_ids)):
                    if not ids:
                        continue
                    await s.execute(delete(PriceSnapshot).where(
                        PriceSnapshot.region_type == region_type,
                        PriceSnapshot.region_id.in_(ids),
                    ))
                    await s.execute(delete(PriceDistribution).where(
                        PriceDistribution.region_type == region_type,
                        PriceDistribution.region_id.in_(ids),
                    ))
                await s.execute(delete(District).where(District.city_id.in_(city_ids)))
                await s.execute(delete(City).where(City.id.in_(city_ids)))
            job_ids = (
                (await s.execute(select(CrawlJob.id).where(CrawlJob.source == TEST_JOB_SOURCE)))
                .scalars().all()
            )
            if job_ids:
                await s.execute(delete(CrawlLog).where(CrawlLog.job_id.in_(job_ids)))
                await s.execute(delete(CrawlJob).where(CrawlJob.id.in_(job_ids)))


@pytest.fixture(scope="module")
def engine():
    return create_async_engine(settings.database_url, echo=False)


@pytest.fixture(scope="module")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def cleanup_test_rows(session_factory):
    """测试前后各清一次：前置清历史泄漏，后置清本轮写入，并失效 API 缓存。"""
    await _purge_test_rows(session_factory)
    yield
    await _purge_test_rows(session_factory)
    from redis.asyncio import Redis

    from app.core.cache import invalidate_api_caches

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await invalidate_api_caches(redis, "cleanup")
    finally:
        await redis.aclose()


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
        count = await upsert_price_snapshots(session, records, "city", city_id, source="creprice")
        assert count == 2

    async def test_upsert_updates_price(self, session):
        city_map = await upsert_cities(session, [CityInfo(name="更新快照市", code="upd_snap_city")])
        city_id = city_map["upd_snap_city"]

        records = [{"year_month": "2025-03", "supply_price": 8000}]
        await upsert_price_snapshots(session, records, "city", city_id, source="creprice")

        updated = [{"year_month": "2025-03", "supply_price": 9999}]
        await upsert_price_snapshots(session, updated, "city", city_id, source="creprice")

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
        await upsert_price_snapshots(session, records, "city", city_id, source="creprice")
        await upsert_price_snapshots(session, records, "city", city_id, source="creprice")

        result = await session.execute(
            select(func.count()).select_from(PriceSnapshot).where(
                PriceSnapshot.region_type == "city",
                PriceSnapshot.region_id == city_id,
            )
        )
        assert result.scalar() == 1

    async def test_empty_records(self, session):
        assert await upsert_price_snapshots(session, [], "city", 999, source="creprice") == 0

    async def test_sources_coexist_same_month(self, session):
        """不同源写同城同月：两行共存、互不覆盖（源独立存储）。"""
        city_map = await upsert_cities(session, [CityInfo(name="共存市", code="coex_city")])
        city_id = city_map["coex_city"]

        await upsert_price_snapshots(
            session, [{"year_month": "2024-12", "supply_price": 9000}],
            "city", city_id, source="creprice",
        )
        await upsert_price_snapshots(
            session, [{"year_month": "2024-12", "supply_price": 13000}],
            "city", city_id, source="listing_annual_58",
        )

        result = await session.execute(
            select(PriceSnapshot).where(
                PriceSnapshot.region_type == "city",
                PriceSnapshot.region_id == city_id,
                PriceSnapshot.year_month == "2024-12",
            ).order_by(PriceSnapshot.source)
        )
        rows = list(result.scalars())
        assert [(r.source, r.supply_price) for r in rows] == [
            ("creprice", 9000),
            ("listing_annual_58", 13000),
        ]


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
