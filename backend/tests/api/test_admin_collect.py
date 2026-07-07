"""管理端采集 API 集成测试（外部 HTTP 与 pipeline 打桩）。"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.collector.base import CityInfo
from app.collector.sources.creprice import CrepriceSource
from app.core.database import async_session_factory
from app.models.admin_job import AdminJob
from app.models.city import City
from app.pipeline.runner import PipelineRunner

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]

FAKE_CODES = ["zztest1", "zztest2"]


@pytest_asyncio.fixture(loop_scope="session")
async def fake_cities():
    """向 city 表插入两个测试城市，测试后连同产生的 collect 任务一并清理。"""
    async with async_session_factory() as s:
        s.add_all(
            [
                City(name="测试城一", code="zztest1", province="测试省"),
                City(name="测试城二", code="zztest2", province="测试省"),
            ]
        )
        await s.commit()
    yield FAKE_CODES
    async with async_session_factory() as s:
        jobs = (await s.execute(select(AdminJob).where(AdminJob.kind == "collect"))).scalars()
        for job in jobs:
            codes = (job.payload or {}).get("city_codes", [])
            if set(codes) & set(FAKE_CODES):
                await s.delete(job)
        await s.execute(delete(City).where(City.code.in_(FAKE_CODES)))
        await s.commit()


async def _wait_job_final(client, headers, job_id: int, timeout: float = 5.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/api/v1/admin/jobs/{job_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in ("success", "failed"):
            return data
        await asyncio.sleep(0.05)
    raise TimeoutError(f"job #{job_id} 未在 {timeout}s 内结束")


class TestRefreshCities:
    async def test_refresh_upserts_cities(self, client, admin_headers, monkeypatch, fake_cities):
        monkeypatch.setattr(
            CrepriceSource,
            "fetch_cities",
            lambda self: [CityInfo(name="测试城一", code="zztest1", province="测试省")],
        )
        resp = await client.post("/api/v1/admin/collect/cities/refresh", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    async def test_refresh_forbidden_for_user(self, client, auth_headers):
        resp = await client.post("/api/v1/admin/collect/cities/refresh", headers=auth_headers)
        assert resp.status_code == 403


class TestCityCoverage:
    async def test_coverage_of_seeded_city(self, client, admin_headers):
        resp = await client.get("/api/v1/admin/collect/cities?keyword=qz", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        qz = next(c for c in data["items"] if c["code"] == "qz")
        # dev DB 已有泉州数据：区县与最新月份非空
        assert qz["district_count"] > 0
        assert qz["latest_month"] is not None

    async def test_keyword_and_province_filter(self, client, admin_headers, fake_cities):
        resp = await client.get(
            "/api/v1/admin/collect/cities?province=测试省", headers=admin_headers
        )
        data = resp.json()
        assert data["total"] == 2
        assert all(c["province"] == "测试省" for c in data["items"])
        assert all(c["district_count"] == 0 and c["latest_month"] is None for c in data["items"])

        resp = await client.get(
            "/api/v1/admin/collect/cities?keyword=测试城一", headers=admin_headers
        )
        assert resp.json()["total"] == 1


class TestSubmitCollect:
    async def test_collect_job_success_flow(
        self, client, admin_headers, monkeypatch, fake_cities
    ):
        async def fake_run(self, source_name, city_code):
            await asyncio.sleep(0.01)
            return {"snapshots": 5, "distributions": 2, "logs": 3, "errors": []}

        monkeypatch.setattr(PipelineRunner, "run", fake_run)

        resp = await client.post(
            "/api/v1/admin/collect", json={"city_codes": FAKE_CODES}, headers=admin_headers
        )
        assert resp.status_code == 202
        job = resp.json()
        assert job["kind"] == "collect"
        assert job["progress_total"] == 2

        final = await _wait_job_final(client, admin_headers, job["id"])
        assert final["status"] == "success"
        assert final["progress_done"] == 2
        assert [r["ok"] for r in final["result"]] == [True, True]
        assert final["result"][0]["snapshots"] == 5

    async def test_partial_failure_still_success(
        self, client, admin_headers, monkeypatch, fake_cities
    ):
        async def flaky_run(self, source_name, city_code):
            if city_code == "zztest2":
                raise RuntimeError("城市页 404")
            return {"snapshots": 1, "distributions": 0, "logs": 1, "errors": []}

        monkeypatch.setattr(PipelineRunner, "run", flaky_run)

        resp = await client.post(
            "/api/v1/admin/collect", json={"city_codes": FAKE_CODES}, headers=admin_headers
        )
        final = await _wait_job_final(client, admin_headers, resp.json()["id"])
        assert final["status"] == "success"
        oks = {r["city"]: r["ok"] for r in final["result"]}
        assert oks == {"zztest1": True, "zztest2": False}
        assert "404" in final["result"][1]["error"]

    async def test_all_failed_marks_job_failed(
        self, client, admin_headers, monkeypatch, fake_cities
    ):
        async def broken_run(self, source_name, city_code):
            raise RuntimeError("网络中断")

        monkeypatch.setattr(PipelineRunner, "run", broken_run)

        resp = await client.post(
            "/api/v1/admin/collect", json={"city_codes": ["zztest1"]}, headers=admin_headers
        )
        final = await _wait_job_final(client, admin_headers, resp.json()["id"])
        assert final["status"] == "failed"
        assert "失败" in final["error"]

    async def test_mutex_409_while_running(
        self, client, admin_headers, monkeypatch, fake_cities
    ):
        release = asyncio.Event()

        async def slow_run(self, source_name, city_code):
            await release.wait()
            return {"snapshots": 0, "distributions": 0, "logs": 0, "errors": []}

        monkeypatch.setattr(PipelineRunner, "run", slow_run)

        resp = await client.post(
            "/api/v1/admin/collect", json={"city_codes": ["zztest1"]}, headers=admin_headers
        )
        assert resp.status_code == 202
        job_id = resp.json()["id"]
        try:
            resp2 = await client.post(
                "/api/v1/admin/collect", json={"city_codes": ["zztest2"]}, headers=admin_headers
            )
            assert resp2.status_code == 409
            assert resp2.json()["code"] == "JOB_CONFLICT"
        finally:
            release.set()
        await _wait_job_final(client, admin_headers, job_id)

    async def test_unknown_code_422(self, client, admin_headers, fake_cities):
        resp = await client.post(
            "/api/v1/admin/collect", json={"city_codes": ["nope_xyz"]}, headers=admin_headers
        )
        assert resp.status_code == 422

    async def test_empty_payload_422(self, client, admin_headers):
        resp = await client.post("/api/v1/admin/collect", json={}, headers=admin_headers)
        assert resp.status_code == 422

    async def test_collect_forbidden_for_user(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/admin/collect", json={"city_codes": ["qz"]}, headers=auth_headers
        )
        assert resp.status_code == 403


class TestJobsQuery:
    async def test_list_jobs_with_kind_filter(self, client, admin_headers):
        resp = await client.get("/api/v1/admin/jobs?kind=collect", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(j["kind"] == "collect" for j in data["items"])

    async def test_job_detail_404(self, client, admin_headers):
        resp = await client.get("/api/v1/admin/jobs/99999999", headers=admin_headers)
        assert resp.status_code == 404

    async def test_jobs_forbidden_for_user(self, client, auth_headers):
        resp = await client.get("/api/v1/admin/jobs", headers=auth_headers)
        assert resp.status_code == 403
