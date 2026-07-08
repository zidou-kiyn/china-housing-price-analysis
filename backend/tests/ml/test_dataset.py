"""多源训练集构建器单测（合成数据）：校准、插值、去重、权重、指纹。"""

import numpy as np
import pytest

from app.ml.dataset import (
    ANNUAL_SAMPLE_WEIGHT,
    _annual_to_monthly,
    _ratio_for_year,
    build_multi_source_series,
    estimate_basis_ratio_curve,
)
from app.ml.features import (
    RegionSeries,
    build_inference_row,
    build_region_series,
    build_training_frame,
    feature_columns,
    shift_month,
)
from app.ml.train import ModelStore, _fit_random_forest, train_random_forest


def _row(region_id: int, ym: str, price, region_type: str = "city") -> dict:
    return {
        "region_type": region_type,
        "region_id": region_id,
        "year_month": ym,
        "supply_price": price,
    }


def _monthly_rows(
    region_id: int,
    start: str,
    months: int,
    base: float = 10000,
    step: float = 100,
    region_type: str = "city",
) -> list[dict]:
    rows, m = [], start
    for t in range(months):
        rows.append(_row(region_id, m, base + t * step, region_type))
        m = shift_month(m, 1)
    return rows


def _annual_rows(region_id: int, values: dict[str, float], region_type: str = "city") -> list[dict]:
    return [_row(region_id, f"{year}-12", price, region_type) for year, price in values.items()]


class TestRatioCurve:
    def test_yearly_median_from_drifting_pairs(self):
        """比值漂移数据：逐年分段，2011 年两对取 median。"""
        rows = {
            "kaggle_lianjia": [
                _row(1, "2010-12", 7920),
                _row(1, "2011-12", 9660),
                _row(2, "2011-12", 11000),
            ],
            "listing_annual_58": [
                _row(1, "2010-12", 10000),
                _row(1, "2011-12", 10000),
                _row(2, "2011-12", 10000),
            ],
        }
        curve, pairs = estimate_basis_ratio_curve(rows)
        assert pairs == 3
        assert curve == {"2010": 0.792, "2011": 1.033}  # median(0.966, 1.1)

    def test_listing_monthly_source_produces_no_pairs(self):
        """creprice 是月度挂牌口径，不构成 成交/挂牌 对。"""
        rows = {
            "creprice": [_row(1, "2020-12", 9000)],
            "listing_annual_58": [_row(1, "2020-12", 10000)],
        }
        curve, pairs = estimate_basis_ratio_curve(rows)
        assert curve == {} and pairs == 0

    def test_no_overlap_returns_empty(self):
        rows = {
            "kaggle_lianjia": [_row(1, "2020-01", 9000)],
            "listing_annual_58": [_row(1, "2020-12", 10000)],
        }
        curve, pairs = estimate_basis_ratio_curve(rows)
        assert curve == {} and pairs == 0

    def test_ratio_for_year_nearest_extension(self):
        curve = {"2011": 0.8, "2013": 1.0}
        assert _ratio_for_year(curve, "2011") == 0.8
        assert _ratio_for_year(curve, "2010") == 0.8  # 早于曲线 → 最近端点
        assert _ratio_for_year(curve, "2015") == 1.0  # 晚于曲线 → 最近端点
        assert _ratio_for_year(curve, "2012") == 0.8  # 区间内缺年、距离并列 → 较早年
        assert _ratio_for_year({}, "2012") == 1.0  # 无曲线 → 不校准


class TestAnnualToMonthly:
    def test_calibrate_then_interpolate(self):
        rows = _annual_rows(1, {"2020": 10000, "2021": 13000, "2022": 12000})
        curve = {"2020": 0.8, "2021": 1.0}
        series, calibrated = _annual_to_monthly(rows, curve)

        assert calibrated == 3
        rs = series[0]
        assert (rs.months[0], rs.months[-1]) == ("2020-12", "2022-12")  # 首末点外不外推
        assert len(rs.months) == 25
        assert rs.prices[0] == pytest.approx(8000)  # 10000 × 0.8
        assert rs.prices[12] == pytest.approx(13000)  # 13000 × 1.0
        assert rs.prices[24] == pytest.approx(12000)  # 2022 超出曲线 → 沿用 2021 比值
        # 年点之间线性插值：2021-06 是 8000→13000 的第 6/12 步
        assert rs.prices[6] == pytest.approx(8000 + (13000 - 8000) * 6 / 12)
        assert rs.interp_flags == [1] * 25  # 12 月真实点亦是年度口径，全部标记
        assert rs.weights == [ANNUAL_SAMPLE_WEIGHT] * 25

    def test_empty_curve_means_no_calibration(self):
        rows = _annual_rows(1, {"2020": 10000, "2021": 12000})
        series, calibrated = _annual_to_monthly(rows, {})
        assert calibrated == 0
        assert series[0].prices[0] == pytest.approx(10000)


class TestBuildMultiSourceSeries:
    def test_real_monthly_wins_no_duplicate_months(self):
        """同 (region, month) 双源共存：真实月度优先，缺口用年度插值。"""
        monthly = _monthly_rows(1, "2020-06", 12)  # 2020-06..2021-05, 10000..11100
        annual = _annual_rows(1, {"2019": 12000, "2020": 12000, "2021": 12000})
        series_list, meta = build_multi_source_series(
            {"creprice": monthly, "listing_annual_58": annual}
        )

        assert len(series_list) == 1
        rs = series_list[0]
        assert len(rs.months) == len(set(rs.months)) == 25  # 2019-12..2021-12 无重复月
        i = rs.months.index("2020-12")  # 双源重叠月 → 月度真实值
        assert rs.prices[i] == pytest.approx(10600)
        assert rs.interp_flags[i] == 0 and rs.weights[i] == 1.0
        j = rs.months.index("2020-03")  # 月度序列之前 → 年度插值
        assert rs.prices[j] == pytest.approx(12000)
        assert rs.interp_flags[j] == 1 and rs.weights[j] == ANNUAL_SAMPLE_WEIGHT
        k = rs.months.index("2021-08")  # 月度序列之后 → 年度插值
        assert rs.interp_flags[k] == 1
        assert meta.ratio_pairs == 0  # creprice 挂牌月度不构成校准对

    def test_gap_between_sources_interpolated_and_downweighted(self):
        """两段序列之间仍缺的月：线性插值 + flag=1 + 降权。"""
        monthly = _monthly_rows(1, "2020-01", 3)  # 10000, 10100, 10200
        annual = _annual_rows(1, {"2021": 12000})
        series_list, _ = build_multi_source_series(
            {"creprice": monthly, "listing_annual_58": annual}
        )

        rs = series_list[0]
        assert (rs.months[0], rs.months[-1]) == ("2020-01", "2021-12")
        assert len(rs.months) == 24
        gap = rs.months.index("2020-04")
        assert rs.interp_flags[gap] == 1 and rs.weights[gap] == ANNUAL_SAMPLE_WEIGHT
        # 2020-03=10200 → 2021-12=12000 共 21 步线性
        assert rs.prices[gap] == pytest.approx(10200 + (12000 - 10200) / 21)

    def test_transaction_overlap_calibrates_annual_gap(self):
        """北京式场景：成交月度与年度挂牌重叠 → 曲线校准年度缺口段。"""
        monthly = _monthly_rows(1, "2015-01", 24, base=20000, step=0)  # 全 20000 成交
        annual = _annual_rows(1, {"2015": 25000, "2016": 25000, "2018": 25000})
        series_list, meta = build_multi_source_series(
            {"kaggle_lianjia": monthly, "listing_annual_58": annual}
        )

        assert meta.ratio_curve == {"2015": 0.8, "2016": 0.8}
        assert meta.ratio_pairs == 2
        assert meta.calibrated_rows == 3
        rs = series_list[0]
        assert rs.basis == "transaction"  # 真实月度点最多的源决定口径
        assert (rs.months[0], rs.months[-1]) == ("2015-01", "2018-12")
        i = rs.months.index("2016-12")  # 重叠月取真实成交值
        assert rs.prices[i] == pytest.approx(20000) and rs.interp_flags[i] == 0
        j = rs.months.index("2017-06")  # 缺口段：25000 × 0.8 = 20000 校准后插值
        assert rs.prices[j] == pytest.approx(20000)
        assert rs.interp_flags[j] == 1 and rs.weights[j] == ANNUAL_SAMPLE_WEIGHT
        assert rs.prices[-1] == pytest.approx(20000)  # 2018 超出曲线 → 沿用 2016 比值

    def test_two_monthly_sources_dedup_by_priority(self):
        creprice = _monthly_rows(1, "2020-01", 12, base=10000, step=0)
        kaggle = _monthly_rows(1, "2020-06", 12, base=20000, step=0)
        series_list, _ = build_multi_source_series(
            {"creprice": creprice, "kaggle_lianjia": kaggle}
        )

        rs = series_list[0]
        assert (rs.months[0], rs.months[-1]) == ("2020-01", "2021-05")
        overlap = rs.months.index("2020-08")  # 重叠月 → 高优先级 creprice
        assert rs.prices[overlap] == pytest.approx(10000)
        after = rs.months.index("2021-03")  # creprice 之外 → kaggle 真实值
        assert rs.prices[after] == pytest.approx(20000)
        assert rs.interp_flags[after] == 0 and rs.weights[after] == 1.0

    def test_pure_monthly_single_source_unchanged(self):
        """纯月度路径回归：仅 creprice 时序列与改造前完全一致。"""
        rows = _monthly_rows(1, "2020-01", 20, region_type="district")
        series_list, meta = build_multi_source_series({"creprice": rows})
        baseline = build_region_series(rows)

        assert len(series_list) == len(baseline) == 1
        rs, base_rs = series_list[0], baseline[0]
        assert rs.months == base_rs.months and rs.prices == base_rs.prices
        assert rs.weights is None and rs.interp_flags is None and rs.basis == "listing"

        frame = build_training_frame(series_list, 3)
        assert len(frame) == 17  # 样本数不回退
        assert (frame["weight"] == 1.0).all()
        assert (frame["is_annual_interp"] == 0).all()
        assert (frame["basis_enc"] == 0).all()
        assert meta.per_source == {
            "creprice": {"rows": 20, "regions": 1, "min_month": "2020-01", "max_month": "2021-08"}
        }
        assert meta.ratio_curve == {} and meta.ratio_pairs == 0 and meta.calibrated_rows == 0

    def test_annual_only_region_produces_series(self):
        """仅年度数据的区域也能进训练集（此前为死资产）。"""
        annual = _annual_rows(7, {"2018": 9000, "2019": 9500, "2020": 10000})
        series_list, meta = build_multi_source_series({"listing_annual_58": annual})

        assert len(series_list) == 1
        rs = series_list[0]
        assert len(rs.months) == 25 and rs.interp_flags == [1] * 25
        assert meta.per_source["listing_annual_58"]["regions"] == 1

    def test_unknown_source_defaults_to_monthly_listing(self):
        series_list, meta = build_multi_source_series({"mystery": _monthly_rows(1, "2020-01", 15)})
        assert series_list[0].basis == "listing"
        assert meta.per_source["mystery"]["rows"] == 15

    def test_fingerprint_stable_and_sensitive(self):
        _, meta1 = build_multi_source_series({"creprice": _monthly_rows(1, "2020-01", 15)})
        _, meta2 = build_multi_source_series({"creprice": _monthly_rows(1, "2020-01", 15)})
        assert meta1.fingerprint == meta2.fingerprint
        assert len(meta1.fingerprint) == 16

        changed = _monthly_rows(1, "2020-01", 15)
        changed[3]["supply_price"] += 1
        _, meta3 = build_multi_source_series({"creprice": changed})
        assert meta3.fingerprint != meta1.fingerprint


class TestWeightsAndTraining:
    def test_training_frame_carries_weights_flags_basis(self):
        rs = RegionSeries(
            region_type="city",
            region_id=1,
            months=["2020-01", "2020-02", "2020-03", "2020-04", "2020-05", "2020-06"],
            prices=[10000, 10100, 10200, 10300, 10400, 10500],
            basis="transaction",
            weights=[1, 1, 1, 0.3, 0.3, 0.3],
            interp_flags=[0, 0, 0, 1, 1, 1],
        )
        frame = build_training_frame([rs], n_lags=3)

        assert list(frame["weight"]) == [0.3, 0.3, 0.3]  # 样本 idx 3..5 的权重
        assert list(frame["is_annual_interp"]) == [1, 1, 1]
        assert (frame["basis_enc"] == 1).all()
        assert "weight" not in feature_columns(3)  # 权重不是特征

    def test_sample_weight_changes_fit(self):
        x = np.array([[float(i)] for i in range(10)])
        y = np.array([0.0] * 5 + [100.0] * 5)
        m_all, _ = _fit_random_forest(x, y, np.ones(10))
        m_zero, _ = _fit_random_forest(x, y, np.array([1.0] * 5 + [0.0] * 5))
        assert m_all.predict([[9.0]])[0] > 50
        assert m_zero.predict([[9.0]])[0] < 1  # 后半权重 0 → 学不到 100

    def test_train_records_dataset_meta_and_new_features(self, tmp_path):
        store = ModelStore(tmp_path)
        monthly = _monthly_rows(1, "2019-01", 40, region_type="district")
        annual = _annual_rows(
            2, {"2018": 9000, "2019": 9500, "2020": 10000, "2021": 10500, "2022": 11000}
        )
        series_list, ds_meta = build_multi_source_series(
            {"creprice": monthly, "listing_annual_58": annual}
        )
        meta = train_random_forest(series_list, store, dataset_meta=ds_meta.to_dict())

        assert meta["dataset"]["per_source"]["listing_annual_58"]["rows"] == 5
        assert meta["dataset"]["fingerprint"] == ds_meta.fingerprint
        assert meta["features"][-2:] == ["basis_enc", "is_annual_interp"]
        _, loaded_meta = store.load_latest("random_forest")
        assert loaded_meta["dataset"]["fingerprint"] == ds_meta.fingerprint

    def test_inference_row_slices_by_old_feature_list(self):
        """旧模型 meta.features 不含新列：按其切片仍可构造推理行。"""
        series = build_region_series(_monthly_rows(1, "2020-01", 15))[0]
        old_cols = feature_columns(6)[:-2]  # 模拟旧模型特征列
        x = build_inference_row(series, 6, "2021-04", old_cols)
        assert list(x.columns) == old_cols
