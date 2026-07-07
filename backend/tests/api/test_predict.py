"""预测 API 端到端测试（真实库数据训练 + 推理落库）。"""

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.prediction import Prediction

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def trained_model(client, admin_headers, tmp_path_factory, monkeypatch_session):
    """在临时目录训练泉州模型，避免污染真实 models/。"""
    model_dir = tmp_path_factory.mktemp("models")
    monkeypatch_session.setattr(settings, "ml_model_dir", str(model_dir))

    resp = await client.post(
        "/api/v1/admin/predict/train", json={"city_code": "qz"}, headers=admin_headers
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


@pytest.fixture(scope="session")
def monkeypatch_session():
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


async def _district_with_full_history(client, auth_headers) -> int:
    """取泉州数据月份最多的区县（丰泽区等 13 个月）。"""
    resp = await client.get(
        "/api/v1/rank?region_type=district&city_code=qz", headers=auth_headers
    )
    items = [i for i in resp.json()["items"] if i["supply_price"] is not None]
    return items[0]["region_id"]


class TestTrain:
    async def test_train_returns_meta(self, trained_model):
        assert trained_model["model_name"] == "random_forest"
        assert trained_model["model_version"].startswith("v")
        assert trained_model["training_samples"] >= 20
        assert "r2" in trained_model["metrics"]

    async def test_train_requires_admin(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/admin/predict/train", json={}, headers=auth_headers
        )
        assert resp.status_code == 403

    async def test_train_unknown_city_404(self, client, admin_headers):
        resp = await client.post(
            "/api/v1/admin/predict/train", json={"city_code": "nope"}, headers=admin_headers
        )
        assert resp.status_code == 404


class TestPredict:
    async def test_three_month_prediction(self, client, auth_headers, trained_model):
        region_id = await _district_with_full_history(client, auth_headers)
        resp = await client.get(
            f"/api/v1/predict/{region_id}?region_type=district", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model_version"] == trained_model["model_version"]
        assert len(data["predictions"]) == 3
        for p in data["predictions"]:
            assert p["confidence_lower"] <= p["predicted_price"] <= p["confidence_upper"]

        # 已落库
        engine = create_async_engine(settings.database_url)
        sf = async_sessionmaker(engine, expire_on_commit=False)
        async with sf() as s:
            saved = (
                (
                    await s.execute(
                        select(Prediction).where(
                            Prediction.region_type == "district",
                            Prediction.region_id == region_id,
                            Prediction.model_version == trained_model["model_version"],
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(saved) == 3
            await s.execute(
                delete(Prediction).where(
                    Prediction.region_id == region_id,
                    Prediction.model_version == trained_model["model_version"],
                )
            )
            await s.commit()
        await engine.dispose()

    async def test_requires_auth(self, client, trained_model):
        resp = await client.get("/api/v1/predict/1?region_type=district")
        assert resp.status_code == 401

    async def test_nonexistent_region_404(self, client, auth_headers, trained_model):
        resp = await client.get(
            "/api/v1/predict/99999999?region_type=district", headers=auth_headers
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "REGION_NOT_FOUND"

    async def test_sparse_region_404(self, client, auth_headers, admin_headers, trained_model):
        """数据不足 12 个月的区县（如泉港区）应返回 PREDICTION_NOT_FOUND。"""
        resp = await client.get(
            "/api/v1/rank?region_type=district&city_code=qz", headers=auth_headers
        )
        sparse = [i for i in resp.json()["items"] if i["supply_price"] is None]
        if not sparse:
            pytest.skip("库中无数据不足的区县")
        resp = await client.get(
            f"/api/v1/predict/{sparse[0]['region_id']}?region_type=district",
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "PREDICTION_NOT_FOUND"
