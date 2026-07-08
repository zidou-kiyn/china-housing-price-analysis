"""价格 API 集成测试。"""

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.core.database import async_session_factory
from app.models.city import City
from app.models.price_snapshot import PriceSnapshot
from app.pipeline.loaders import upsert_price_snapshots

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(loop_scope="session")
async def multi_source_city_id():
    """seed 双源城市：2024-12 creprice+58 共存，2020-12 仅 58 年度。"""
    async with async_session_factory() as s:
        city = City(name="双源测试市", code="t_dualsrc", province="单测省")
        s.add(city)
        await s.commit()
        city_id = city.id
        await upsert_price_snapshots(
            s, [{"year_month": "2024-12", "supply_price": 9000}],
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
                PriceSnapshot.region_type == "city", PriceSnapshot.region_id == city_id
            )
        )
        await s.execute(delete(City).where(City.id == city_id))
        await s.commit()


class TestPriceTrend:
    async def test_returns_trend_data(self, client, qz_city_id):
        resp = await client.get(f"/api/v1/prices/trend?region_type=city&region_id={qz_city_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 12

    async def test_trend_point_shape(self, client, qz_city_id):
        resp = await client.get(f"/api/v1/prices/trend?region_type=city&region_id={qz_city_id}")
        point = resp.json()[0]
        assert "year_month" in point
        assert "supply_price" in point
        assert "source" in point  # 溯源注记，前端标注口径用

    async def test_months_filter(self, client, qz_city_id):
        resp = await client.get(f"/api/v1/prices/trend?region_type=city&region_id={qz_city_id}&months=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    async def test_empty_for_nonexistent_region(self, client):
        resp = await client.get("/api/v1/prices/trend?region_type=city&region_id=999999")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_invalid_region_type(self, client):
        resp = await client.get("/api/v1/prices/trend?region_type=invalid&region_id=1")
        assert resp.status_code == 422

    async def test_trend_merges_multi_source_by_priority(self, client, multi_source_city_id):
        """双源同月：默认 trend 每月一点，月度源优先。"""
        resp = await client.get(
            f"/api/v1/prices/trend?region_type=city&region_id={multi_source_city_id}"
        )
        assert resp.status_code == 200
        points = resp.json()
        assert [(p["year_month"], p["supply_price"], p["source"]) for p in points] == [
            ("2020-12", 11000, "listing_annual_58"),
            ("2024-12", 9000, "creprice"),  # 与 58 的 13000 共存，但月度优先
        ]


class TestPriceTrendSeries:
    async def test_series_split_by_source(self, client, multi_source_city_id):
        resp = await client.get(
            f"/api/v1/prices/trend/series?region_type=city&region_id={multi_source_city_id}"
        )
        assert resp.status_code == 200
        series = resp.json()
        assert [s["source"] for s in series] == ["creprice", "listing_annual_58"]  # 优先级排序

        creprice = series[0]
        assert creprice["granularity"] == "monthly"
        assert [p["supply_price"] for p in creprice["points"]] == [9000]

        annual = series[1]
        assert annual["granularity"] == "annual"
        assert annual["basis"] == "listing"
        assert [(p["year_month"], p["supply_price"]) for p in annual["points"]] == [
            ("2020-12", 11000), ("2024-12", 13000),
        ]

    async def test_series_empty_region(self, client):
        resp = await client.get("/api/v1/prices/trend/series?region_type=city&region_id=999999")
        assert resp.status_code == 200
        assert resp.json() == []


class TestPriceDistribution:
    async def test_returns_distribution(self, client, qz_city_id):
        resp = await client.get(f"/api/v1/prices/distribution?region_type=city&region_id={qz_city_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0

    async def test_distribution_shape(self, client, qz_city_id):
        resp = await client.get(f"/api/v1/prices/distribution?region_type=city&region_id={qz_city_id}")
        item = resp.json()[0]
        assert "price_range_low" in item
        assert "price_range_high" in item
        assert "percentage" in item

    async def test_empty_for_nonexistent(self, client):
        resp = await client.get("/api/v1/prices/distribution?region_type=city&region_id=999999")
        assert resp.status_code == 200
        assert resp.json() == []


class TestDistrictOverview:
    async def test_returns_overview(self, client):
        resp = await client.get("/api/v1/prices/overview?city_code=qz")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3

    async def test_overview_has_prices(self, client):
        resp = await client.get("/api/v1/prices/overview?city_code=qz")
        item = resp.json()[0]
        assert "supply_price" in item
        assert "name" in item
        assert "code" in item

    async def test_404_nonexistent_city(self, client):
        resp = await client.get("/api/v1/prices/overview?city_code=nonexistent")
        assert resp.status_code == 404
