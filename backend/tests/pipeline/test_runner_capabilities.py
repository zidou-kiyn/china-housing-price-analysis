"""管线能力自适应测试：最小能力源（仅城市 + 城市级时序）应跳过区县/分布阶段且不报错。

用真实 dev DB（同 test_runner_live 的连接方式），测试后自清理假城市数据并注销假源。
不打网络，故不标 slow。
"""

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.collector.base import BaseSource, CityInfo, DataType, RawRecord, SourceRegistry
from app.core.config import settings
from app.models.city import City
from app.models.crawl_job import CrawlJob
from app.models.crawl_log import CrawlLog
from app.models.price_snapshot import PriceSnapshot
from app.pipeline.runner import PipelineRunner

pytestmark = pytest.mark.asyncio(loop_scope="module")

_FAKE_SOURCE = "_captest_minimal"
_FAKE_CITY = "captestcity"


class _MinimalSource(BaseSource):
    """只声明 CITIES + PRICE_TIMELINE 能力；不实现区县/分布（若被调用会 NotImplementedError）。"""

    source_name = _FAKE_SOURCE
    base_url = "https://example.test"
    capabilities = frozenset({DataType.CITIES, DataType.PRICE_TIMELINE})

    def __init__(self, http_client=None) -> None:  # 不建真实 http 客户端
        pass

    def fetch_cities(self):
        return [CityInfo(name="能力测试城", code=_FAKE_CITY, province="测试省")]

    def fetch_price_timeline(self, city_code, district_code="allsq1"):
        return RawRecord(
            source=self.source_name,
            city_code=city_code,
            data_type="price_timeline",
            records=[
                {"year_month": "2025-01", "supply_price": 10000,
                 "attention_price": None, "value_price": None, "sample_count": 5},
                {"year_month": "2025-02", "supply_price": 10100,
                 "attention_price": None, "value_price": None, "sample_count": 6},
            ],
        )


@pytest.fixture(scope="module")
def session_factory():
    engine = create_async_engine(settings.database_url, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def stats(session_factory):
    SourceRegistry.register(_FAKE_SOURCE, _MinimalSource)
    try:
        result = await PipelineRunner(session_factory).run(_FAKE_SOURCE, _FAKE_CITY)
        yield result
    finally:
        SourceRegistry._registry.pop(_FAKE_SOURCE, None)
        async with session_factory() as s:
            city = (
                await s.execute(select(City).where(City.code == _FAKE_CITY))
            ).scalar_one_or_none()
            if city:
                await s.execute(
                    delete(PriceSnapshot).where(
                        PriceSnapshot.region_type == "city",
                        PriceSnapshot.region_id == city.id,
                    )
                )
            job_ids = (
                await s.execute(select(CrawlJob.id).where(CrawlJob.source == _FAKE_SOURCE))
            ).scalars().all()
            if job_ids:
                await s.execute(delete(CrawlLog).where(CrawlLog.job_id.in_(job_ids)))
                await s.execute(delete(CrawlJob).where(CrawlJob.id.in_(job_ids)))
            if city:
                await s.execute(delete(City).where(City.id == city.id))
            await s.commit()


class TestCapabilityGating:
    async def test_no_errors(self, stats):
        # 若 runner 误调用了未实现的 fetch_districts/fetch_price_distribution，会记入 errors
        assert stats["errors"] == []

    async def test_has_city_snapshots(self, stats):
        assert stats["snapshots"] > 0

    async def test_skips_distribution(self, stats):
        # 源不支持 PRICE_DISTRIBUTION → 不产出分布，也不因缺方法报错
        assert stats["distributions"] == 0

    async def test_snapshot_records_source(self, session_factory, stats):
        # 入库快照写入了溯源 source 列
        async with session_factory() as s:
            city = (
                await s.execute(select(City).where(City.code == _FAKE_CITY))
            ).scalar_one()
            sources = (
                await s.execute(
                    select(PriceSnapshot.source).where(
                        PriceSnapshot.region_type == "city",
                        PriceSnapshot.region_id == city.id,
                    )
                )
            ).scalars().all()
        assert sources and all(src == _FAKE_SOURCE for src in sources)
