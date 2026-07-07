"""排行 / 对比 / 地图 API 集成测试。"""

import pytest
import pytest_asyncio

from app.core.cache import redis_client

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def qz_district_ids(client):
    await redis_client.delete("api:districts:qz")
    resp = await client.get("/api/v1/cities/qz/districts")
    assert resp.status_code == 200
    return [d["id"] for d in resp.json()]


class TestRank:
    async def test_district_rank_sorted_desc(self, client):
        resp = await client.get("/api/v1/rank?region_type=district&city_code=qz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3
        prices = [i["supply_price"] for i in data["items"] if i["supply_price"] is not None]
        assert prices == sorted(prices, reverse=True)

    async def test_rank_item_shape(self, client):
        resp = await client.get("/api/v1/rank?region_type=district&city_code=qz")
        item = resp.json()["items"][0]
        for key in ("region_id", "region_name", "supply_price", "yoy_pct", "mom_pct", "year_month"):
            assert key in item

    async def test_rank_asc_order(self, client):
        resp = await client.get("/api/v1/rank?region_type=district&city_code=qz&sort_order=asc")
        prices = [i["supply_price"] for i in resp.json()["items"] if i["supply_price"] is not None]
        assert prices == sorted(prices)

    async def test_rank_pagination(self, client):
        resp = await client.get("/api/v1/rank?region_type=district&city_code=qz&page_size=2")
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] >= 3

    async def test_rank_city_level(self, client):
        resp = await client.get("/api/v1/rank?region_type=city")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_rank_invalid_region_type(self, client):
        resp = await client.get("/api/v1/rank?region_type=invalid")
        assert resp.status_code == 422

    async def test_rank_404_nonexistent_city(self, client):
        resp = await client.get("/api/v1/rank?region_type=district&city_code=nonexistent")
        assert resp.status_code == 404

    async def test_rank_cached_after_first_call(self, client):
        await client.get("/api/v1/rank?region_type=district&city_code=qz")
        assert await redis_client.exists("api:rank:district:qz:supply_price:desc")


class TestCompare:
    async def test_two_regions(self, client, qz_district_ids):
        ids = ",".join(map(str, qz_district_ids[:2]))
        resp = await client.get(f"/api/v1/compare?region_type=district&region_ids={ids}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["price_type"] == "supply_price"
        assert len(data["regions"]) == 2
        for region in data["regions"]:
            assert len(region["data"]) <= 12
            assert "year_month" in region["data"][0]
            assert "price" in region["data"][0]

    async def test_months_filter(self, client, qz_district_ids):
        ids = ",".join(map(str, qz_district_ids[:2]))
        resp = await client.get(f"/api/v1/compare?region_type=district&region_ids={ids}&months=3")
        for region in resp.json()["regions"]:
            assert len(region["data"]) <= 3

    async def test_too_few_ids(self, client, qz_district_ids):
        resp = await client.get(f"/api/v1/compare?region_type=district&region_ids={qz_district_ids[0]}")
        assert resp.status_code == 422

    async def test_too_many_ids(self, client):
        resp = await client.get("/api/v1/compare?region_type=district&region_ids=1,2,3,4,5,6")
        assert resp.status_code == 422

    async def test_non_integer_ids(self, client):
        resp = await client.get("/api/v1/compare?region_type=district&region_ids=a,b")
        assert resp.status_code == 422

    async def test_404_nonexistent_region(self, client):
        resp = await client.get("/api/v1/compare?region_type=district&region_ids=999998,999999")
        assert resp.status_code == 404


class TestMapHeat:
    async def test_returns_all_districts(self, client, qz_district_ids):
        resp = await client.get("/api/v1/map/heat?city_code=qz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["city_code"] == "qz"
        assert data["region_type"] == "district"
        assert len(data["data"]) == len(qz_district_ids)

    async def test_heat_item_shape(self, client):
        resp = await client.get("/api/v1/map/heat?city_code=qz")
        item = resp.json()["data"][0]
        for key in ("region_id", "region_name", "price"):
            assert key in item

    async def test_404_nonexistent_city(self, client):
        resp = await client.get("/api/v1/map/heat?city_code=nonexistent")
        assert resp.status_code == 404
