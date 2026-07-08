"""ModelStore 活跃指针与版本列表单元测试。"""

import math

import pytest

from app.ml.features import build_region_series, shift_month
from app.ml.train import ModelStore, train_model


def _rows(months: int = 60):
    rows = []
    month = "2019-01"
    for t in range(months):
        season = 300 * math.sin(2 * math.pi * (t % 12) / 12)
        for region_id in (1, 2, 3):
            rows.append(
                {
                    "region_type": "district",
                    "region_id": region_id,
                    "year_month": month,
                    "supply_price": 8000 + region_id * 1500 + t * 40 + season,
                }
            )
        month = shift_month(month, 1)
    return rows


@pytest.fixture
def store(tmp_path):
    return ModelStore(tmp_path)


@pytest.fixture
def both_trained(store):
    series = build_region_series(_rows())
    rf_meta = train_model("random_forest", series, store)
    xgb_meta = train_model("xgboost", series, store)
    return rf_meta, xgb_meta


class TestActivePointer:
    def test_no_pointer_falls_back_to_latest_rf(self, store, both_trained):
        rf_meta, _ = both_trained
        assert store.get_active() is None
        _, meta = store.load_active()
        assert meta["model_name"] == "random_forest"
        assert meta["version"] == rf_meta["version"]

    def test_set_and_load_active(self, store, both_trained):
        _, xgb_meta = both_trained
        store.set_active("xgboost", xgb_meta["version"])
        assert store.get_active() == {"model_name": "xgboost", "version": xgb_meta["version"]}
        _, meta = store.load_active()
        assert meta["model_name"] == "xgboost"

    def test_set_active_unknown_version_raises(self, store, both_trained):
        with pytest.raises(ValueError):
            store.set_active("xgboost", "v9.9")
        with pytest.raises(ValueError):
            store.set_active("lightgbm", "v1.0")

    def test_stale_pointer_falls_back(self, store, both_trained):
        _, xgb_meta = both_trained
        store.set_active("xgboost", xgb_meta["version"])
        pkl = store._model_dir("xgboost") / f"{xgb_meta['version']}.pkl"
        pkl.unlink()
        _, meta = store.load_active()
        assert meta["model_name"] == "random_forest"

    def test_empty_store_returns_none(self, store):
        assert store.load_active() is None


class TestListAll:
    def test_lists_both_models(self, store, both_trained):
        metas = store.list_all()
        assert [(m["model_name"], m["version"]) for m in metas] == [
            ("random_forest", "v1.0"),
            ("xgboost", "v1.0"),
        ]

    def test_empty_dir(self, tmp_path):
        assert ModelStore(tmp_path / "nope").list_all() == []


def _save_dummy(
    store,
    model_name: str,
    version: str,
    mape: float = 5.0,
    real_mape: float | None = None,
) -> None:
    """写入一个廉价的伪版本（pkl 内容不参与断言，仅占位两文件）。"""
    meta = {"model_name": model_name, "version": version, "metrics": {"mape": mape}}
    if real_mape is not None:
        meta["metrics_real_monthly"] = {"mape": real_mape}
    store.save(model_name, version, {"dummy": True}, meta)


class TestDelete:
    def test_delete_removes_both_files(self, store):
        _save_dummy(store, "random_forest", "v1.0")
        _save_dummy(store, "random_forest", "v1.1")

        store.delete("random_forest", "v1.0")

        model_dir = store._model_dir("random_forest")
        assert not (model_dir / "v1.0.pkl").exists()
        assert not (model_dir / "v1.0_meta.json").exists()
        assert store.versions("random_forest") == ["v1.1"]

    def test_delete_active_raises(self, store):
        _save_dummy(store, "random_forest", "v1.0")
        store.set_active("random_forest", "v1.0")
        with pytest.raises(ValueError):
            store.delete("random_forest", "v1.0")
        assert store.versions("random_forest") == ["v1.0"]

    def test_delete_missing_raises(self, store):
        _save_dummy(store, "random_forest", "v1.0")
        with pytest.raises(FileNotFoundError):
            store.delete("random_forest", "v9.9")
        with pytest.raises(FileNotFoundError):
            store.delete("lightgbm", "v1.0")

    def test_delete_rejects_path_traversal(self, store, tmp_path):
        """model_name/version 含 ".." 不得逃出 base_dir 删除任意文件。"""
        victim_pkl = tmp_path.parent / "victim.pkl"
        victim_meta = tmp_path.parent / "victim_meta.json"
        victim_pkl.write_bytes(b"x")
        victim_meta.write_text("{}", encoding="utf-8")
        _save_dummy(store, "random_forest", "v1.0")
        try:
            with pytest.raises(ValueError, match="非法"):
                store.delete("..", "victim")
            with pytest.raises(ValueError, match="非法"):
                store.delete("random_forest", "../../victim")
            with pytest.raises(ValueError, match="非法"):
                store.delete(".", "v1.0")
            assert victim_pkl.exists()
            assert victim_meta.exists()
            assert store.versions("random_forest") == ["v1.0"]
        finally:
            victim_pkl.unlink(missing_ok=True)
            victim_meta.unlink(missing_ok=True)


class TestCleanup:
    def test_keeps_last_n_plus_active(self, store):
        for minor in range(5):  # v1.0 ~ v1.4
            _save_dummy(store, "random_forest", f"v1.{minor}")
        store.set_active("random_forest", "v1.0")

        deleted = store.cleanup(keep_last=2)

        assert deleted == [
            {"model_name": "random_forest", "version": "v1.1"},
            {"model_name": "random_forest", "version": "v1.2"},
        ]
        # 活跃 v1.0 保留，最近 2 个 v1.3/v1.4 保留
        assert store.versions("random_forest") == ["v1.0", "v1.3", "v1.4"]
        assert store.get_active() == {"model_name": "random_forest", "version": "v1.0"}

    def test_covers_all_models(self, store):
        for minor in range(4):
            _save_dummy(store, "random_forest", f"v1.{minor}")
            _save_dummy(store, "xgboost", f"v1.{minor}")

        deleted = store.cleanup(keep_last=3)

        assert deleted == [
            {"model_name": "random_forest", "version": "v1.0"},
            {"model_name": "xgboost", "version": "v1.0"},
        ]

    def test_nothing_to_delete(self, store):
        _save_dummy(store, "random_forest", "v1.0")
        assert store.cleanup(keep_last=3) == []
        assert store.versions("random_forest") == ["v1.0"]

    def test_empty_dir(self, tmp_path):
        assert ModelStore(tmp_path / "nope").cleanup() == []


class TestBestVersions:
    def test_lowest_mape_per_model(self, store):
        _save_dummy(store, "random_forest", "v1.0", mape=4.75)
        _save_dummy(store, "random_forest", "v1.1", mape=1.95)
        _save_dummy(store, "random_forest", "v1.2", mape=3.10)
        _save_dummy(store, "xgboost", "v1.0", mape=2.26)

        assert store.best_versions() == {"random_forest": "v1.1", "xgboost": "v1.0"}

    def test_skips_versions_without_mape(self, store):
        _save_dummy(store, "random_forest", "v1.0", mape=2.0)
        store.save(
            "random_forest",
            "v1.1",
            {"dummy": True},
            {"model_name": "random_forest", "version": "v1.1"},  # 无 metrics
        )
        assert store.best_versions() == {"random_forest": "v1.0"}

    def test_prefers_real_monthly_mape_over_headline(self, store):
        """年度扩充训练的版本按 metrics_real_monthly 评最佳，headline 虚低不作数。

        复刻实况：v1.7 headline 0.25/real 2.71 vs v1.8 headline 0.31/real 2.70
        —— headline 口径下 v1.7 胜，诚实口径下 v1.8 胜。
        """
        _save_dummy(store, "random_forest", "v1.7", mape=0.25, real_mape=2.71)
        _save_dummy(store, "random_forest", "v1.8", mape=0.31, real_mape=2.70)
        assert store.best_versions() == {"random_forest": "v1.8"}

    def test_falls_back_to_headline_without_real_monthly(self, store):
        """旧 meta（纯月度训练，headline 即诚实口径）回退 metrics.mape 参与比较。"""
        _save_dummy(store, "random_forest", "v1.0", mape=3.5)  # 无 real_monthly
        _save_dummy(store, "random_forest", "v1.1", mape=0.2, real_mape=2.9)
        assert store.best_versions() == {"random_forest": "v1.1"}

    def test_null_real_monthly_falls_back(self, store):
        """metrics_real_monthly 为 null（验证集无真实月度样本）时回退 headline。"""
        store.save(
            "random_forest",
            "v1.0",
            {"dummy": True},
            {
                "model_name": "random_forest",
                "version": "v1.0",
                "metrics": {"mape": 1.0},
                "metrics_real_monthly": None,
            },
        )
        _save_dummy(store, "random_forest", "v1.1", mape=0.5, real_mape=2.0)
        assert store.best_versions() == {"random_forest": "v1.0"}

    def test_empty_store(self, store):
        assert store.best_versions() == {}
