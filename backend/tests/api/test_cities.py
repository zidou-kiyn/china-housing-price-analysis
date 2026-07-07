"""城市/区县 API 集成测试。"""

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.cache import redis_client
from app.core.database import async_session_factory
from app.models.city import City
from app.models.price_snapshot import PriceSnapshot

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(loop_scope="session")
async def city_snapshot_only():
    """一个无区县、仅有城市级快照的城市（模拟 Kaggle 城市级源覆盖）。"""
    code = "zzsnaponly"
    async with async_session_factory() as s:
        city = City(name="仅快照城", code=code, province="测试省")
        s.add(city)
        await s.flush()
        s.add(
            PriceSnapshot(
                region_type="city", region_id=city.id, year_month="2016-05",
                supply_price=40000, sample_count=10, source="kaggle_lianjia",
            )
        )
        await s.commit()
    await redis_client.delete("api:cities")
    yield code
    async with async_session_factory() as s:
        city = (await s.execute(select(City).where(City.code == code))).scalar_one_or_none()
        if city:
            await s.execute(
                delete(PriceSnapshot).where(
                    PriceSnapshot.region_type == "city", PriceSnapshot.region_id == city.id
                )
            )
            await s.execute(delete(City).where(City.id == city.id))
            await s.commit()
    await redis_client.delete("api:cities")


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

    async def test_includes_city_with_only_city_snapshot(self, client, city_snapshot_only):
        # 无区县但有城市级快照的城市应出现（多源城市级历史源可见性）
        resp = await client.get("/api/v1/cities")
        codes = [c["code"] for c in resp.json()]
        assert city_snapshot_only in codes

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
