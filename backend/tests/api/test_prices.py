"""价格 API 集成测试。"""

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]


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
