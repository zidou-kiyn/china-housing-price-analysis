"""训练 / 推理链路单元测试（合成数据）。"""

import math

import pytest

from app.ml.features import build_region_series, shift_month
from app.ml.predict import rolling_predict
from app.ml.train import ModelStore, train_model, train_random_forest


def _synthetic_rows(regions: int = 3, months: int = 60):
    """带趋势 + 季节性的可学习序列（无随机噪声，保证确定性）。"""
    rows = []
    for region_id in range(1, regions + 1):
        base = 8000 + region_id * 1500
        month = "2019-01"
        for t in range(months):
            season = 300 * math.sin(2 * math.pi * (t % 12) / 12)
            rows.append(
                {
                    "region_type": "district",
                    "region_id": region_id,
                    "year_month": month,
                    "supply_price": base + t * 40 + season,
                }
            )
            month = shift_month(month, 1)
    return rows


@pytest.fixture
def store(tmp_path):
    return ModelStore(tmp_path)


@pytest.fixture
def trained(store):
    series = build_region_series(_synthetic_rows())
    meta = train_random_forest(series, store, city_codes=["qz"])
    return series, meta


class TestTrain:
    def test_metrics_meet_baseline(self, trained):
        _, meta = trained
        assert meta["metrics"]["r2"] >= 0.85
        assert meta["metrics"]["mape"] <= 5

    def test_meta_persisted(self, store, trained):
        _, meta = trained
        assert meta["n_lags"] == 12
        assert meta["training_samples"] > 0
        loaded = store.load_latest("random_forest")
        assert loaded is not None
        _, loaded_meta = loaded
        assert loaded_meta["version"] == meta["version"] == "v1.0"
        assert loaded_meta["city_codes"] == ["qz"]

    def test_version_increments(self, store, trained):
        series, _ = trained
        meta2 = train_random_forest(series, store)
        assert meta2["version"] == "v1.1"
        assert store.versions("random_forest") == ["v1.0", "v1.1"]

    def test_adaptive_lag_downgrade(self, store):
        # 每区域 13 个月：lag_12 仅 1 样本/区 ×3 <20 → 降到 lag_6（7×3=21 ≥20）
        series = build_region_series(_synthetic_rows(regions=3, months=13))
        meta = train_random_forest(series, store)
        assert meta["n_lags"] == 6

    def test_insufficient_data_raises(self, store):
        series = build_region_series(_synthetic_rows(regions=1, months=4))
        with pytest.raises(ValueError):
            train_random_forest(series, store)


class TestTrainXgboost:
    def test_metrics_meet_baseline(self, store):
        series = build_region_series(_synthetic_rows())
        meta = train_model("xgboost", series, store, city_codes=["qz"])
        assert meta["metrics"]["r2"] >= 0.85
        assert meta["ci_strategy"] == "residual"
        assert meta["resid_std"] >= 0

    def test_cv_recorded_and_beats_rf_mape(self, store, trained):
        series, rf_meta = trained
        xgb_meta = train_model("xgboost", series, store)
        assert xgb_meta["cv"] is not None
        assert xgb_meta["cv"]["folds"] == 3
        assert set(xgb_meta["cv"]["best_params"]) == {"n_estimators", "max_depth", "learning_rate"}
        assert len(xgb_meta["cv"]["fold_mapes"]) == 3
        assert xgb_meta["metrics"]["mape"] <= rf_meta["metrics"]["mape"]

    def test_small_sample_skips_cv(self, store):
        # 每区域 13 个月 → lag_6 时 21 个样本，train 切分后 <30 → 跳过 CV
        series = build_region_series(_synthetic_rows(regions=3, months=13))
        meta = train_model("xgboost", series, store)
        assert meta["cv"] is None

    def test_unknown_algorithm_raises(self, store):
        series = build_region_series(_synthetic_rows())
        with pytest.raises(ValueError):
            train_model("lightgbm", series, store)

    def test_versions_isolated_per_model(self, store, trained):
        series, _ = trained
        train_model("xgboost", series, store)
        assert store.versions("random_forest") == ["v1.0"]
        assert store.versions("xgboost") == ["v1.0"]


class TestXgboostRollingPredict:
    def test_horizon_and_interval(self, store):
        series = build_region_series(_synthetic_rows())
        train_model("xgboost", series, store)
        model, meta = store.load_latest("xgboost")
        points = rolling_predict(model, meta, series[0], months_ahead=3)
        assert len(points) == 3
        for p in points:
            assert p.confidence_lower <= p.predicted_price <= p.confidence_upper

    def test_prediction_in_plausible_range(self, store):
        series = build_region_series(_synthetic_rows())
        train_model("xgboost", series, store)
        model, meta = store.load_latest("xgboost")
        last_price = series[0].prices[-1]
        for p in rolling_predict(model, meta, series[0], months_ahead=3):
            assert abs(p.predicted_price - last_price) / last_price < 0.2


class TestRollingPredict:
    def test_three_month_horizon(self, store, trained):
        series, meta = trained
        model, meta = store.load_latest("random_forest")
        points = rolling_predict(model, meta, series[0], months_ahead=3)

        assert len(points) == 3
        last_month = series[0].months[-1]
        assert [p.target_month for p in points] == [
            shift_month(last_month, 1),
            shift_month(last_month, 2),
            shift_month(last_month, 3),
        ]

    def test_confidence_interval_contains_prediction(self, store, trained):
        series, _ = trained
        model, meta = store.load_latest("random_forest")
        for p in rolling_predict(model, meta, series[0], months_ahead=3):
            assert p.confidence_lower <= p.predicted_price <= p.confidence_upper

    def test_prediction_in_plausible_range(self, store, trained):
        series, _ = trained
        model, meta = store.load_latest("random_forest")
        points = rolling_predict(model, meta, series[0], months_ahead=3)
        last_price = series[0].prices[-1]
        for p in points:
            assert abs(p.predicted_price - last_price) / last_price < 0.2

    def test_short_history_raises(self, store, trained):
        _, _ = trained
        model, meta = store.load_latest("random_forest")
        short = build_region_series(_synthetic_rows(regions=1, months=8))[0]
        with pytest.raises(ValueError):
            rolling_predict(model, meta, short, months_ahead=3)
