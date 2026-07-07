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
