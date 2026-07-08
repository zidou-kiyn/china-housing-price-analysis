"""训练 / 推理链路单元测试（合成数据）。"""

import math

import numpy as np
import pandas as pd
import pytest

from app.ml.features import build_region_series, shift_month
from app.ml.predict import rolling_predict
from app.ml.train import (
    ModelStore,
    _baseline_metrics,
    _per_region_metrics,
    _stratified_metrics,
    train_model,
    train_random_forest,
)


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


class TestBaselineMetrics:
    def test_hand_computed_values(self):
        frame_val = pd.DataFrame(
            {"lag_1": [100.0, 200.0], "lag_12": [80.0, 160.0], "y": [110.0, 220.0]}
        )
        baselines = _baseline_metrics(frame_val, n_lags=12)
        # last_value: 误差 10/20 → mae 15；mape = mean(10/110, 20/220)*100 = 9.09
        assert baselines["last_value"] == {"mae": 15.0, "mape": 9.09}
        # seasonal: 误差 30/60 → mae 45；mape = mean(30/110, 60/220)*100 = 27.27
        assert baselines["seasonal"] == {"mae": 45.0, "mape": 27.27}

    def test_seasonal_omitted_below_12_lags(self):
        frame_val = pd.DataFrame({"lag_1": [100.0], "y": [110.0]})
        baselines = _baseline_metrics(frame_val, n_lags=6)
        assert baselines["last_value"] == {"mae": 10.0, "mape": 9.09}
        assert baselines["seasonal"] is None


class TestPerRegionMetrics:
    def test_hand_computed_groups(self):
        frame_val = pd.DataFrame(
            {"region_type_enc": [1, 1, 0], "region_id": [7, 7, 3], "y": [100.0, 200.0, 400.0]}
        )
        y_pred = np.array([110.0, 220.0, 400.0])
        prm = _per_region_metrics(frame_val, y_pred)
        assert prm["regions"] == 2
        assert prm["median_mape"] == 5.0  # median(10.0, 0.0)
        assert prm["worst"][0] == {
            "region_type": "district",
            "region_id": 7,
            "mape": 10.0,
            "samples": 2,
        }
        assert prm["worst"][1] == {"region_type": "city", "region_id": 3, "mape": 0.0, "samples": 1}


class TestStratifiedMetrics:
    def test_real_monthly_layer_split(self):
        frame_val = pd.DataFrame({"is_annual_interp": [0, 1, 0], "y": [100.0, 200.0, 300.0]})
        metrics_real, strata = _stratified_metrics(frame_val, np.array([90.0, 260.0, 300.0]))
        assert strata == {"real_monthly": 2, "annual_interp": 1}
        # 仅真实月度行 (100→90, 300→300)：mae 5.0，mape 5.0
        assert metrics_real["mae"] == 5.0
        assert metrics_real["mape"] == 5.0

    def test_all_annual_returns_none(self):
        frame_val = pd.DataFrame({"is_annual_interp": [1, 1], "y": [100.0, 200.0]})
        metrics_real, strata = _stratified_metrics(frame_val, np.array([100.0, 200.0]))
        assert metrics_real is None
        assert strata == {"real_monthly": 0, "annual_interp": 2}


class TestTrainMetaEvaluation:
    def test_rf_cv_recorded(self, trained):
        _, meta = trained
        assert meta["cv"] is not None
        assert meta["cv"]["folds"] == 3
        assert set(meta["cv"]["best_params"]) == {"n_estimators", "max_depth"}
        assert len(meta["cv"]["fold_mapes"]) == 3

    def test_rf_small_sample_skips_cv(self, store):
        # 每区域 13 个月 → lag_6 时 21 个样本，train 切分后 16 <30 → 跳过 CV
        series = build_region_series(_synthetic_rows(regions=3, months=13))
        meta = train_random_forest(series, store)
        assert meta["cv"] is None

    def test_baselines_in_meta(self, trained):
        _, meta = trained
        assert set(meta["baselines"]["last_value"]) == {"mae", "mape"}
        assert set(meta["baselines"]["seasonal"]) == {"mae", "mape"}  # n_lags=12
        assert isinstance(meta["beats_baseline"], bool)
        assert meta["beats_baseline"] == (
            meta["metrics"]["mape"] < meta["baselines"]["last_value"]["mape"]
        )

    def test_seasonal_baseline_none_when_short_window(self, store):
        series = build_region_series(_synthetic_rows(regions=3, months=13))
        meta = train_random_forest(series, store)  # n_lags 自适应降到 6
        assert meta["baselines"]["last_value"] is not None
        assert meta["baselines"]["seasonal"] is None

    def test_per_region_metrics_in_meta(self, trained):
        _, meta = trained
        prm = meta["per_region_metrics"]
        assert prm["regions"] == 3
        assert len(prm["worst"]) == 3  # 不足 5 个区域时全部列出
        assert prm["median_mape"] >= 0
        assert all(
            {"region_type", "region_id", "mape", "samples"} == set(w) for w in prm["worst"]
        )

    def test_pure_monthly_strata(self, trained):
        _, meta = trained
        assert meta["validation_strata"] == {
            "real_monthly": meta["validation_samples"],
            "annual_interp": 0,
        }
        assert meta["metrics_real_monthly"] == meta["metrics"]

    def test_mixed_strata_reports_real_monthly_layer(self, store):
        # 区域 2 整段标注为年度插值：验证集两层都有样本，真实月度层单独出指标
        series = build_region_series(_synthetic_rows(regions=2, months=60))
        annual = series[1]
        annual.interp_flags = [1] * len(annual.months)
        annual.weights = [0.3] * len(annual.months)
        meta = train_random_forest(series, store)
        assert meta["validation_strata"]["real_monthly"] > 0
        assert meta["validation_strata"]["annual_interp"] > 0
        assert meta["metrics_real_monthly"] is not None
        assert meta["metrics_real_monthly"] != meta["metrics"]


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
