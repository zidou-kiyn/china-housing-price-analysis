"""预测 API 端到端测试（真实库数据训练 + 推理落库，训练走后台任务）。"""

import asyncio
import json
import shutil
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.source_policy import SOURCE_META
from app.ml.train import ModelStore
from app.models.admin_job import AdminJob
from app.models.prediction import Prediction
from app.models.price_snapshot import PriceSnapshot

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]

_TRAIN_JOB_IDS: list[int] = []


async def _train_and_wait(client, admin_headers, payload: dict, timeout: float = 30.0) -> dict:
    """提交训练任务并等待完成，返回展平的训练结果（model_version 等）。"""
    resp = await client.post("/api/v1/admin/predict/train", json=payload, headers=admin_headers)
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["id"]
    _TRAIN_JOB_IDS.append(job_id)

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = (await client.get(f"/api/v1/admin/jobs/{job_id}", headers=admin_headers)).json()
        if job["status"] in ("success", "failed"):
            assert job["status"] == "success", job["error"]
            r = job["result"][0]
            return {
                "model_name": r["model_name"],
                "model_version": r["version"],
                "metrics": r["metrics"],
                "training_samples": r["training_samples"],
            }
        await asyncio.sleep(0.1)
    raise TimeoutError(f"训练任务 #{job_id} 超时未结束")


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _clean_train_jobs():
    yield
    if not _TRAIN_JOB_IDS:
        return
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        await s.execute(delete(AdminJob).where(AdminJob.id.in_(_TRAIN_JOB_IDS)))
        await s.commit()
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def trained_model(client, admin_headers, tmp_path_factory, monkeypatch_session):
    """在临时目录训练泉州模型，避免污染真实 models/。"""
    model_dir = tmp_path_factory.mktemp("models")
    monkeypatch_session.setattr(settings, "ml_model_dir", str(model_dir))

    return await _train_and_wait(client, admin_headers, {"city_codes": ["qz"]})


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


async def _city_ids_by_source_mix() -> tuple[int | None, int | None]:
    """扫描城市级快照的源构成，返回 (仅年度源城市, 月度+年度混合城市)；缺则 None。"""
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        rows = (
            await s.execute(
                select(PriceSnapshot.region_id, PriceSnapshot.source, func.count())
                .where(PriceSnapshot.region_type == "city")
                .group_by(PriceSnapshot.region_id, PriceSnapshot.source)
            )
        ).all()
    await engine.dispose()

    by_city: dict[int, dict[str, int]] = {}
    for region_id, source, n in rows:
        by_city.setdefault(region_id, {})[source] = n

    def _gran(source: str) -> str:
        return SOURCE_META.get(source, {}).get("granularity", "monthly")

    annual_only = mixed = None
    for region_id in sorted(by_city):
        sources = by_city[region_id]
        grans = {_gran(s) for s in sources}
        if annual_only is None and grans == {"annual"} and sum(sources.values()) >= 3:
            annual_only = region_id  # ≥3 个年度点 → 插值后 ≥25 个月，够预测窗口
        if mixed is None and grans == {"annual", "monthly"}:
            monthly_rows = sum(n for s, n in sources.items() if _gran(s) == "monthly")
            if monthly_rows >= 12:  # 月度段够长，保证真实月度序列不被缺失率门槛丢弃
                mixed = region_id
    return annual_only, mixed


async def _cleanup_predictions(region_type: str, region_id: int, model_versions: list[str]) -> None:
    """按 (region, 本测试所训版本) 精确清理落库预测行，不动库中其它行。"""
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s:
        await s.execute(
            delete(Prediction).where(
                Prediction.region_type == region_type,
                Prediction.region_id == region_id,
                Prediction.model_version.in_(model_versions),
            )
        )
        await s.commit()
    await engine.dispose()


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
            "/api/v1/admin/predict/train", json={"city_codes": ["nope"]}, headers=admin_headers
        )
        assert resp.status_code == 404

    async def test_train_mutex_409(self, client, admin_headers, monkeypatch, trained_model):
        """训练进行中再次提交返回 409（train_model 打桩拖慢）。"""
        import time

        from app.api.v1 import predictions

        real_training = predictions.run_training

        def slow_training(*args, **kwargs):
            time.sleep(1.0)
            return real_training(*args, **kwargs)

        monkeypatch.setattr(predictions, "run_training", slow_training)

        resp = await client.post(
            "/api/v1/admin/predict/train", json={"city_codes": ["qz"]}, headers=admin_headers
        )
        assert resp.status_code == 202
        job_id = resp.json()["id"]
        _TRAIN_JOB_IDS.append(job_id)

        resp2 = await client.post(
            "/api/v1/admin/predict/train", json={"city_codes": ["qz"]}, headers=admin_headers
        )
        assert resp2.status_code == 409
        assert resp2.json()["code"] == "JOB_CONFLICT"

        # 等它跑完，避免影响后续用例
        deadline = asyncio.get_event_loop().time() + 30
        while asyncio.get_event_loop().time() < deadline:
            job = (
                await client.get(f"/api/v1/admin/jobs/{job_id}", headers=admin_headers)
            ).json()
            if job["status"] in ("success", "failed"):
                break
            await asyncio.sleep(0.1)

    async def test_train_failure_marks_job_failed(
        self, client, admin_headers, monkeypatch, trained_model
    ):
        from app.api.v1 import predictions

        def broken_training(*args, **kwargs):
            raise ValueError("训练样本不足")

        monkeypatch.setattr(predictions, "run_training", broken_training)

        resp = await client.post(
            "/api/v1/admin/predict/train", json={"city_codes": ["qz"]}, headers=admin_headers
        )
        assert resp.status_code == 202
        job_id = resp.json()["id"]
        _TRAIN_JOB_IDS.append(job_id)

        deadline = asyncio.get_event_loop().time() + 10
        while asyncio.get_event_loop().time() < deadline:
            job = (
                await client.get(f"/api/v1/admin/jobs/{job_id}", headers=admin_headers)
            ).json()
            if job["status"] in ("success", "failed"):
                break
            await asyncio.sleep(0.1)
        assert job["status"] == "failed"
        assert "训练样本不足" in job["error"]


class TestModelSwitch:
    async def test_xgboost_train_list_switch_predict(
        self, client, auth_headers, admin_headers, trained_model
    ):
        xgb = await _train_and_wait(
            client, admin_headers, {"model_name": "xgboost", "city_codes": ["qz"]}
        )
        assert xgb["model_name"] == "xgboost"

        # 未设置指针：两种模型都列出、均未激活
        resp = await client.get("/api/v1/admin/predict/models", headers=admin_headers)
        assert resp.status_code == 200
        models = resp.json()
        assert {m["model_name"] for m in models} == {"random_forest", "xgboost"}
        assert all(not m["is_active"] for m in models)
        # 新训模型透出基线对比字段（train-eval R5）
        assert all(m["beats_baseline"] is not None for m in models)
        assert all(m["baseline_mape"] is not None for m in models)

        # 切换到 xgboost 后预测端点随之切换
        resp = await client.put(
            "/api/v1/admin/predict/models/active",
            json={"model_name": "xgboost", "version": xgb["model_version"]},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        active = [m for m in resp.json() if m["is_active"]]
        assert len(active) == 1
        assert active[0]["model_name"] == "xgboost"

        region_id = await _district_with_full_history(client, auth_headers)
        resp = await client.get(
            f"/api/v1/predict/{region_id}?region_type=district", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["model_name"] == "xgboost"

        # 切回 RF
        resp = await client.put(
            "/api/v1/admin/predict/models/active",
            json={"model_name": "random_forest", "version": trained_model["model_version"]},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        resp = await client.get(
            f"/api/v1/predict/{region_id}?region_type=district", headers=auth_headers
        )
        assert resp.json()["model_name"] == "random_forest"

        # 清理两种模型写入的预测行
        engine = create_async_engine(settings.database_url)
        sf = async_sessionmaker(engine, expire_on_commit=False)
        async with sf() as s:
            await s.execute(
                delete(Prediction).where(
                    Prediction.region_id == region_id,
                    Prediction.model_version.in_(
                        [xgb["model_version"], trained_model["model_version"]]
                    ),
                )
            )
            await s.commit()
        await engine.dispose()

    async def test_switch_unknown_version_404(self, client, admin_headers, trained_model):
        resp = await client.put(
            "/api/v1/admin/predict/models/active",
            json={"model_name": "xgboost", "version": "v9.9"},
            headers=admin_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "MODEL_NOT_FOUND"

    async def test_models_requires_admin(self, client, auth_headers):
        resp = await client.get("/api/v1/admin/predict/models", headers=auth_headers)
        assert resp.status_code == 403

    async def test_list_models_old_meta_compat(self, client, admin_headers, trained_model):
        """旧版本 meta（无 baselines 等新字段）list 全链路不报错，新字段为 None。"""
        model_dir = Path(settings.ml_model_dir) / "random_forest"
        old_pkl = model_dir / "v9.0.pkl"
        old_meta_path = model_dir / "v9.0_meta.json"
        shutil.copyfile(model_dir / f"{trained_model['model_version']}.pkl", old_pkl)
        old_meta_path.write_text(
            json.dumps(
                {
                    "model_name": "random_forest",
                    "version": "v9.0",
                    "trained_at": "2026-01-01T00:00:00+00:00",
                    "n_lags": 12,
                    "metrics": {"mae": 100.0, "rmse": 150.0, "mape": 1.5, "r2": 0.9},
                    "training_samples": 100,
                }
            ),
            encoding="utf-8",
        )
        try:
            resp = await client.get("/api/v1/admin/predict/models", headers=admin_headers)
            assert resp.status_code == 200
            legacy = next(m for m in resp.json() if m["version"] == "v9.0")
            assert legacy["beats_baseline"] is None
            assert legacy["baseline_mape"] is None
        finally:
            # 清理伪造版本，避免影响 next_version / 版本列表相关用例
            old_pkl.unlink()
            old_meta_path.unlink()


class TestPredict:
    async def test_three_month_prediction(self, client, auth_headers, trained_model):
        region_id = await _district_with_full_history(client, auth_headers)
        resp = await client.get(
            f"/api/v1/predict/{region_id}?region_type=district", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["model_version"] == trained_model["model_version"]
        assert data["data_quality"] == "monthly"  # 泉州区县仅 creprice 月度源
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


class TestPredictNoActiveModel:
    """空窗期（旧模型全删，等重训）：无活跃模型时预测 API 返回 404 + NO_ACTIVE_MODEL，不 500。"""

    async def test_predict_no_active_model_404(
        self, client, auth_headers, qz_city_id, monkeypatch, tmp_path
    ):
        # 指向空模型目录 → load_active() 为 None（旧模型已全删的空窗态）
        monkeypatch.setattr(settings, "ml_model_dir", str(tmp_path / "empty_models"))
        resp = await client.get(
            f"/api/v1/predict/{qz_city_id}?region_type=city", headers=auth_headers
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "NO_ACTIVE_MODEL"


class TestPredictCoverage:
    """预测覆盖与治理：creprice-first 白名单下的覆盖塌缩 + 旧版本行清理。

    方针（07-08）：训练/预测只认 creprice。年度插值/混合口径预测路径保留但被白名单
    挡在上游、走不到——年度校准/赋形的直接覆盖见 tests/ml/test_dataset.py。
    """

    async def test_annual_only_city_not_predictable(
        self, client, auth_headers, trained_model
    ):
        """creprice-first 覆盖塌缩：仅年度源（无 creprice）的城市不再可预测 → 404。"""
        annual_only, _ = await _city_ids_by_source_mix()
        if annual_only is None:
            pytest.skip("库中无仅年度源的城市")
        resp = await client.get(
            f"/api/v1/predict/{annual_only}?region_type=city", headers=auth_headers
        )
        # 白名单滤掉 58/kaggle → 该城市无 creprice 历史 → 无可用序列
        assert resp.status_code == 404
        assert resp.json()["code"] == "PREDICTION_NOT_FOUND"

    async def test_mixed_source_city_predicts_monthly_only(
        self, client, auth_headers, trained_model
    ):
        """曾经的月度+年度混合城市：白名单下只喂 creprice → 只能是 monthly，绝不 mixed/annual_interp。"""
        _, mixed = await _city_ids_by_source_mix()
        if mixed is None:
            pytest.skip("库中无月度+年度混合源的城市")
        resp = await client.get(
            f"/api/v1/predict/{mixed}?region_type=city", headers=auth_headers
        )
        try:
            # creprice 月度段够长则 monthly 预测；不够则 404——均不再出现 mixed/annual_interp
            assert resp.status_code in (200, 404), resp.text
            if resp.status_code == 200:
                assert resp.json()["data_quality"] == "monthly"
        finally:
            await _cleanup_predictions("city", mixed, [trained_model["model_version"]])

    async def test_old_model_version_rows_cleaned(self, client, auth_headers, trained_model):
        """写入新版本预测后，同 (region, model_name) 的旧版本行被同事务清理。"""
        region_id = await _district_with_full_history(client, auth_headers)
        engine = create_async_engine(settings.database_url)
        sf = async_sessionmaker(engine, expire_on_commit=False)
        async with sf() as s:
            s.add(
                Prediction(
                    region_type="district",
                    region_id=region_id,
                    target_month="2099-01",
                    predicted_price=1,
                    confidence_lower=1,
                    confidence_upper=1,
                    model_name=trained_model["model_name"],
                    model_version="v0.0",
                )
            )
            await s.commit()
        await engine.dispose()

        try:
            resp = await client.get(
                f"/api/v1/predict/{region_id}?region_type=district", headers=auth_headers
            )
            assert resp.status_code == 200, resp.text

            engine = create_async_engine(settings.database_url)
            sf = async_sessionmaker(engine, expire_on_commit=False)
            async with sf() as s:
                versions = (
                    (
                        await s.execute(
                            select(Prediction.model_version).where(
                                Prediction.region_type == "district",
                                Prediction.region_id == region_id,
                                Prediction.model_name == trained_model["model_name"],
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            await engine.dispose()
            assert set(versions) == {trained_model["model_version"]}  # v0.0 已被清理
        finally:
            await _cleanup_predictions(
                "district", region_id, ["v0.0", trained_model["model_version"]]
            )


class TestModelGovernance:
    """模型版本治理（ml-model-governance）：删除、批量清理、最佳标注。"""

    @staticmethod
    def _fabricate(trained_model: dict, version: str, mape: float) -> tuple[Path, Path]:
        """基于已训模型伪造一个版本（复制 pkl + 写最小 meta），返回两文件路径。"""
        model_dir = Path(settings.ml_model_dir) / "random_forest"
        pkl = model_dir / f"{version}.pkl"
        meta_path = model_dir / f"{version}_meta.json"
        shutil.copyfile(model_dir / f"{trained_model['model_version']}.pkl", pkl)
        meta_path.write_text(
            json.dumps(
                {
                    "model_name": "random_forest",
                    "version": version,
                    "trained_at": "2026-01-01T00:00:00+00:00",
                    "n_lags": 12,
                    "metrics": {"mae": 1.0, "rmse": 1.0, "mape": mape, "r2": 0.9},
                    "training_samples": 10,
                }
            ),
            encoding="utf-8",
        )
        return pkl, meta_path

    async def test_delete_nonactive_204(self, client, admin_headers, trained_model):
        pkl, meta_path = self._fabricate(trained_model, "v8.0", mape=99.0)
        resp = await client.delete(
            "/api/v1/admin/predict/models/random_forest/v8.0", headers=admin_headers
        )
        assert resp.status_code == 204, resp.text
        assert not pkl.exists()
        assert not meta_path.exists()

    async def test_delete_active_409(self, client, admin_headers, trained_model):
        resp = await client.put(
            "/api/v1/admin/predict/models/active",
            json={
                "model_name": trained_model["model_name"],
                "version": trained_model["model_version"],
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200

        resp = await client.delete(
            f"/api/v1/admin/predict/models/{trained_model['model_name']}"
            f"/{trained_model['model_version']}",
            headers=admin_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "MODEL_ACTIVE"
        # 文件仍在
        model_dir = Path(settings.ml_model_dir) / trained_model["model_name"]
        assert (model_dir / f"{trained_model['model_version']}.pkl").exists()

    async def test_delete_unknown_404(self, client, admin_headers, trained_model):
        resp = await client.delete(
            "/api/v1/admin/predict/models/random_forest/v9.9", headers=admin_headers
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "MODEL_NOT_FOUND"

    async def test_delete_requires_admin(self, client, auth_headers, trained_model):
        resp = await client.delete(
            "/api/v1/admin/predict/models/random_forest/v9.9", headers=auth_headers
        )
        assert resp.status_code == 403

    async def test_delete_rejects_unsafe_path_params(self, client, admin_headers, trained_model):
        """路径穿越防护：model_name/version 含点等非法字符 → 422，不触达文件系统。"""
        for url in (
            "/api/v1/admin/predict/models/bad.name/v1.0",  # model_name 含点
            "/api/v1/admin/predict/models/%2e%2e/v1.0",  # model_name = ".."
            "/api/v1/admin/predict/models/random_forest/1.0",  # version 缺 v 前缀
            "/api/v1/admin/predict/models/random_forest/v1.0abc",  # version 带尾缀
        ):
            resp = await client.delete(url, headers=admin_headers)
            assert resp.status_code == 422, f"{url} -> {resp.status_code}"

    async def test_cleanup_keeps_recent_and_active(self, client, admin_headers, trained_model):
        """cleanup 后每模型剩最近 keep_last 个 + 活跃版本，active 指针仍有效。"""
        # 确保活跃 = 已训版本（最老 rf 版本之一），验证活跃版不被清理
        resp = await client.put(
            "/api/v1/admin/predict/models/active",
            json={
                "model_name": trained_model["model_name"],
                "version": trained_model["model_version"],
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200

        fabricated = [
            self._fabricate(trained_model, f"v8.{i}", mape=99.0) for i in range(3)
        ]
        store = ModelStore(settings.ml_model_dir)
        expected_deleted = []
        for model_name in ("random_forest", "xgboost"):
            versions = store.versions(model_name)
            keep = set(versions[-2:])
            if model_name == trained_model["model_name"]:
                keep.add(trained_model["model_version"])
            expected_deleted += [
                {"model_name": model_name, "version": v} for v in versions if v not in keep
            ]

        try:
            resp = await client.post(
                "/api/v1/admin/predict/models/cleanup?keep_last=2", headers=admin_headers
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["keep_last"] == 2
            assert body["deleted"] == expected_deleted

            # 剩余版本 = 最近 2 个 + 活跃版；活跃指针仍有效可加载
            rf_left = store.versions("random_forest")
            assert trained_model["model_version"] in rf_left
            assert len(rf_left) <= 3
            assert store.load_active() is not None
            for d in body["deleted"]:
                model_dir = Path(settings.ml_model_dir) / d["model_name"]
                assert not (model_dir / f"{d['version']}.pkl").exists()
                assert not (model_dir / f"{d['version']}_meta.json").exists()
        finally:
            for pkl, meta_path in fabricated:  # 清掉存活的伪造版本，不影响后续用例
                pkl.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)

    async def test_cleanup_requires_admin(self, client, auth_headers, trained_model):
        resp = await client.post(
            "/api/v1/admin/predict/models/cleanup", headers=auth_headers
        )
        assert resp.status_code == 403

    async def test_list_models_marks_best(self, client, admin_headers, trained_model):
        """同模型下 MAPE 最低的版本标注 is_best，且每个模型恰好一个最佳。"""
        pkl, meta_path = self._fabricate(trained_model, "v8.9", mape=0.01)
        try:
            resp = await client.get("/api/v1/admin/predict/models", headers=admin_headers)
            assert resp.status_code == 200
            models = resp.json()
            rf = [m for m in models if m["model_name"] == "random_forest"]
            best_rf = [m for m in rf if m["is_best"]]
            assert [m["version"] for m in best_rf] == ["v8.9"]
            for model_name in {m["model_name"] for m in models}:
                bests = [m for m in models if m["model_name"] == model_name and m["is_best"]]
                assert len(bests) == 1
        finally:
            pkl.unlink()
            meta_path.unlink()
