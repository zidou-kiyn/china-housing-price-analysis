"""管线集成冒烟测试：实际抓取泉州 + 入库 PostgreSQL。

需要：
  - PostgreSQL 运行在 localhost:5432（使用 .env 配置）
  - 已执行 alembic upgrade head
  - 网络可达 creprice.cn
"""

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.city import City
from app.models.crawl_job import CrawlJob
from app.models.crawl_log import CrawlLog
from app.models.district import District
from app.models.price_distribution import PriceDistribution
from app.models.price_snapshot import PriceSnapshot
from app.pipeline.runner import PipelineRunner

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="module")]


@pytest.fixture(scope="module")
def engine():
    return create_async_engine(settings.database_url, echo=False)


@pytest.fixture(scope="module")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pipeline_stats(session_factory):
    """执行一次泉州全量管线，返回统计。module 级别只跑一次。"""
    runner = PipelineRunner(session_factory)
    return await runner.run("creprice", "qz")


class TestPipelineResults:
    async def test_stats_no_errors(self, pipeline_stats):
        assert pipeline_stats["errors"] == []

    async def test_stats_has_snapshots(self, pipeline_stats):
        assert pipeline_stats["snapshots"] > 0

    async def test_stats_has_distributions(self, pipeline_stats):
        assert pipeline_stats["distributions"] > 0

    async def test_city_exists(self, session_factory):
        async with session_factory() as session:
            result = await session.execute(
                select(City).where(City.code == "qz")
            )
            city = result.scalar_one_or_none()
            assert city is not None
            assert "泉" in city.name

    async def test_districts_exist(self, session_factory):
        async with session_factory() as session:
            city = (await session.execute(
                select(City).where(City.code == "qz")
            )).scalar_one()
            result = await session.execute(
                select(func.count()).select_from(District).where(
                    District.city_id == city.id
                )
            )
            count = result.scalar()
            assert count >= 3

    async def test_city_snapshots_12_months(self, session_factory):
        async with session_factory() as session:
            city = (await session.execute(
                select(City).where(City.code == "qz")
            )).scalar_one()
            result = await session.execute(
                select(func.count()).select_from(PriceSnapshot).where(
                    PriceSnapshot.region_type == "city",
                    PriceSnapshot.region_id == city.id,
                )
            )
            count = result.scalar()
            assert count >= 12

    async def test_district_snapshots_exist(self, session_factory):
        async with session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(PriceSnapshot).where(
                    PriceSnapshot.region_type == "district",
                )
            )
            assert result.scalar() > 0

    async def test_price_distribution_exists(self, session_factory):
        async with session_factory() as session:
            city = (await session.execute(
                select(City).where(City.code == "qz")
            )).scalar_one()
            result = await session.execute(
                select(func.count()).select_from(PriceDistribution).where(
                    PriceDistribution.region_type == "city",
                    PriceDistribution.region_id == city.id,
                )
            )
            assert result.scalar() > 0

    async def test_crawl_job_completed(self, session_factory):
        async with session_factory() as session:
            result = await session.execute(
                select(CrawlJob).where(
                    CrawlJob.source == "creprice",
                    CrawlJob.city_code == "qz",
                ).order_by(CrawlJob.id.desc()).limit(1)
            )
            job = result.scalar_one()
            assert job.status == "completed"
            assert job.started_at is not None
            assert job.finished_at is not None

    async def test_crawl_logs_recorded(self, session_factory):
        async with session_factory() as session:
            job = (await session.execute(
                select(CrawlJob).where(
                    CrawlJob.source == "creprice",
                    CrawlJob.city_code == "qz",
                ).order_by(CrawlJob.id.desc()).limit(1)
            )).scalar_one()

            result = await session.execute(
                select(func.count()).select_from(CrawlLog).where(
                    CrawlLog.job_id == job.id
                )
            )
            log_count = result.scalar()
            assert log_count >= 3

    async def test_idempotent_rerun(self, session_factory):
        """重复执行不应产生重复数据。"""
        async with session_factory() as session:
            before = (await session.execute(
                select(func.count()).select_from(PriceSnapshot).where(
                    PriceSnapshot.region_type == "city"
                )
            )).scalar()

        runner = PipelineRunner(session_factory)
        await runner.run("creprice", "qz")

        async with session_factory() as session:
            after = (await session.execute(
                select(func.count()).select_from(PriceSnapshot).where(
                    PriceSnapshot.region_type == "city"
                )
            )).scalar()

        assert after == before
