"""城市/区县 API 集成测试。"""

import pytest

from app.core.cache import redis_client

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]


class TestListCities:
    async def test_returns_list(self, client):
        resp = await client.get("/api/v1/cities")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    async def test_contains_quanzhou(self, client):
        resp = await client.get("/api/v1/cities")
        codes = [c["code"] for c in resp.json()]
        assert "qz" in codes

    async def test_city_shape(self, client):
        resp = await client.get("/api/v1/cities")
        city = resp.json()[0]
        assert "id" in city
        assert "name" in city
        assert "code" in city

    async def test_cache_hit(self, client):
        await client.get("/api/v1/cities")
        cached = await redis_client.get("api:cities")
        assert cached is not None


class TestListDistricts:
    async def test_returns_quanzhou_districts(self, client):
        resp = await client.get("/api/v1/cities/qz/districts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3

    async def test_district_shape(self, client):
        resp = await client.get("/api/v1/cities/qz/districts")
        d = resp.json()[0]
        assert "id" in d
        assert "name" in d
        assert "code" in d

    async def test_404_nonexistent_city(self, client):
        resp = await client.get("/api/v1/cities/nonexistent/districts")
        assert resp.status_code == 404
