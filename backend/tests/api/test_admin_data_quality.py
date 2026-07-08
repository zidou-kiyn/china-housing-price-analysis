"""GET /admin/data-quality/report 集成测试（真实 dev DB，只读端点）。"""

import pytest

from app.core.config import settings

pytestmark = pytest.mark.asyncio(loop_scope="session")

_URL = "/api/v1/admin/data-quality/report"


class TestDataQualityReport:
    async def test_report_sections_present(self, client, admin_headers):
        resp = await client.get(_URL, headers=admin_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        for key in (
            "generated_at",
            "overlap_ratio",
            "creprice_vs_index",
            "annual_vs_index",
            "coverage",
            "model_freshness",
        ):
            assert key in body

        assert body["overlap_ratio"]["outliers_total"] >= 0
        assert len(body["overlap_ratio"]["outliers"]) <= 100
        # 指数已导入时为 ok/no overlap；未导入时降级 "no index data"，不报错
        assert body["creprice_vs_index"]["status"] in ("ok", "no overlap", "no index data")
        assert body["annual_vs_index"]["status"] in ("ok", "no overlap", "no index data")
        assert body["model_freshness"]["status"] in ("fresh", "stale", "unknown")
        for entry in body["coverage"]:
            assert entry["kind"] in ("snapshot", "index")
            assert entry["months_behind"] >= 0

    async def test_report_no_active_model_degrades(
        self, client, admin_headers, monkeypatch, tmp_path
    ):
        """空窗期（无活跃模型）：报告仍正常产出，model_freshness 降级 unknown，不 500。"""
        monkeypatch.setattr(settings, "ml_model_dir", str(tmp_path / "empty_models"))
        resp = await client.get(_URL, headers=admin_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_freshness"]["status"] == "unknown"
        # 审计各节看全源、与训练白名单/模型无关，仍正常产出
        assert "coverage" in body and "overlap_ratio" in body

    async def test_requires_admin(self, client, auth_headers):
        resp = await client.get(_URL, headers=auth_headers)
        assert resp.status_code == 403

    async def test_requires_auth(self, client):
        resp = await client.get(_URL)
        assert resp.status_code == 401
