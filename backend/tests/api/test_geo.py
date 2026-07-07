"""GeoJSON 端点测试（DataV 打桩，geo 目录用临时目录隔离）。"""

import asyncio
import json

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.admin_job import AdminJob
from app.models.city import City
from app.services import geo

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]

GEO_CODE = "zzgeo1"


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def tmp_geo_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "geo_dir", str(tmp_path / "geo"))
    yield tmp_path / "geo"


@pytest_asyncio.fixture(loop_scope="session")
async def geo_city():
    async with async_session_factory() as s:
        s.add(City(name="测试图城", code=GEO_CODE, province="测试省"))
        await s.commit()
    yield GEO_CODE
    async with async_session_factory() as s:
        jobs = (
            await s.execute(select(AdminJob).where(AdminJob.kind == "geo_fetch"))
        ).scalars()
        for job in jobs:
            if GEO_CODE in (job.payload or {}).get("city_codes", []):
                await s.delete(job)
        await s.execute(delete(City).where(City.code == GEO_CODE))
        await s.commit()


async def _wait_job_final(client, headers, job_id: int, timeout: float = 5.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        data = (await client.get(f"/api/v1/admin/jobs/{job_id}", headers=headers)).json()
        if data["status"] in ("success", "failed"):
            return data
        await asyncio.sleep(0.05)
    raise TimeoutError


class TestPublicGeoRead:
    async def test_read_existing_geo(self, client, auth_headers):
        geo.geo_path("zzread").write_text(
            json.dumps({"type": "FeatureCollection", "features": [{"ok": 1}]}),
            encoding="utf-8",
        )
        resp = await client.get("/api/v1/geo/zzread", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["type"] == "FeatureCollection"

    async def test_missing_geo_404(self, client, auth_headers):
        resp = await client.get("/api/v1/geo/zz_none", headers=auth_headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == "GEO_NOT_FOUND"

    async def test_requires_login(self, client):
        resp = await client.get("/api/v1/geo/qz")
        assert resp.status_code == 401


class TestGeoFetchJob:
    async def test_fetch_job_success(self, client, admin_headers, monkeypatch, geo_city):
        async def fake_fetch_geojson(http_client, adcode):
            return {
                "type": "FeatureCollection",
                "features": [{"properties": {"name": "测试区"}}],
            }

        async def fake_backfill(session, http_client):
            # 经 ORM 更新，保证任务体重读时 identity map 内对象已带新 adcode
            city = (
                await session.execute(select(City).where(City.code == GEO_CODE))
            ).scalar_one()
            city.adcode = "999001"
            await session.commit()
            return 1

        monkeypatch.setattr(geo, "fetch_geojson", fake_fetch_geojson)
        monkeypatch.setattr(geo, "backfill_adcodes", fake_backfill)

        resp = await client.post(
            "/api/v1/admin/geo/fetch", json={"city_codes": [GEO_CODE]}, headers=admin_headers
        )
        assert resp.status_code == 202
        final = await _wait_job_final(client, admin_headers, resp.json()["id"])
        assert final["status"] == "success"
        assert final["result"][0] == {"city": GEO_CODE, "ok": True, "districts": 1}
        assert geo.geo_path(GEO_CODE).is_file()

        # 落盘后登录用户立即可读
        resp = await client.get(f"/api/v1/geo/{GEO_CODE}", headers=admin_headers)
        assert resp.status_code == 200

    async def test_no_adcode_marks_city_failed(
        self, client, admin_headers, monkeypatch, geo_city
    ):
        async def fake_backfill(session, http_client):
            return 0  # 索引未命中，adcode 仍为空

        monkeypatch.setattr(geo, "backfill_adcodes", fake_backfill)

        resp = await client.post(
            "/api/v1/admin/geo/fetch", json={"city_codes": [GEO_CODE]}, headers=admin_headers
        )
        final = await _wait_job_final(client, admin_headers, resp.json()["id"])
        # 单城市全失败 → 任务 failed，result 记录原因
        assert final["status"] == "failed"
        assert final["result"][0]["ok"] is False
        assert "adcode" in final["result"][0]["error"]

    async def test_unknown_code_422(self, client, admin_headers):
        resp = await client.post(
            "/api/v1/admin/geo/fetch", json={"city_codes": ["nope_geo"]}, headers=admin_headers
        )
        assert resp.status_code == 422

    async def test_forbidden_for_user(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/admin/geo/fetch", json={"city_codes": ["qz"]}, headers=auth_headers
        )
        assert resp.status_code == 403


class TestAdcodeBackfill:
    async def test_backfill_matches_names(self, monkeypatch, geo_city):
        async def fake_index(http_client):
            return {"测试图城市": "888001", "别的市": "888002"}

        monkeypatch.setattr(geo, "build_city_index", fake_index)

        async with async_session_factory() as s:
            filled = await geo.backfill_adcodes(s, client=None)
            assert filled >= 1

        async with async_session_factory() as s:
            city = (
                await s.execute(select(City).where(City.code == GEO_CODE))
            ).scalar_one()
            # 「测试图城」经 名+市 规则匹配到 测试图城市
            assert city.adcode == "888001"
