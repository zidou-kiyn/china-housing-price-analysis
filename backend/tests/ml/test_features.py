"""特征工程单元测试（合成数据）。"""

from app.ml.features import (
    build_inference_row,
    build_region_series,
    build_training_frame,
    feature_columns,
    shift_month,
)


def _make_rows(months: int, start: str = "2020-01", base: float = 10000, step: float = 100):
    """线性递增序列：price(t) = base + t*step。"""
    rows = []
    month = start
    for t in range(months):
        rows.append(
            {
                "region_type": "district",
                "region_id": 1,
                "year_month": month,
                "supply_price": base + t * step,
            }
        )
        month = shift_month(month, 1)
    return rows


def test_shift_month_cross_year():
    assert shift_month("2025-12", 1) == "2026-01"
    assert shift_month("2026-01", -1) == "2025-12"
    assert shift_month("2026-06", -12) == "2025-06"


def test_build_region_series_interpolates_gap():
    rows = _make_rows(6)
    removed = rows.pop(3)  # 挖掉 2020-04（10300）
    series = build_region_series(rows)

    assert len(series) == 1
    rs = series[0]
    assert removed["year_month"] in rs.months
    idx = rs.months.index(removed["year_month"])
    assert rs.prices[idx] == removed["supply_price"]  # 线性序列插值应精确还原


def test_region_skipped_when_too_sparse():
    rows = _make_rows(12)
    kept = [rows[0], rows[11]]  # 中间 10 个月缺失，缺失率 >30%
    assert build_region_series(kept) == []


def test_training_frame_no_label_leakage():
    rows = _make_rows(20)
    series = build_region_series(rows)
    frame = build_training_frame(series, n_lags=3)

    assert len(frame) == 17  # 20 - 3
    first = frame.iloc[0]
    # 第一条样本对应 t=3（价格 10300），lag_1 应为 t=2 的 10200
    assert first["y"] == 10300
    assert first["lag_1"] == 10200
    assert first["lag_3"] == 10000
    # rolling_mean_3 基于 t-1 及更早（10000,10100,10200），不含当月标签值
    assert first["rolling_mean_3"] == 10100

    assert list(frame.columns[: len(feature_columns(3))]) == feature_columns(3)


def test_mom_yoy_values():
    rows = _make_rows(20)
    series = build_region_series(rows)
    frame = build_training_frame(series, n_lags=13)

    row = frame.iloc[0]  # t=13：上月=11200，上上月=11100，去年同月=10000
    assert abs(row["mom_pct"] - (11200 - 11100) / 11100 * 100) < 1e-9
    assert abs(row["yoy_pct"] - (11200 - 10000) / 10000 * 100) < 1e-9


def test_inference_row_matches_columns():
    series = build_region_series(_make_rows(15))[0]
    x = build_inference_row(series, n_lags=6, target_month="2021-04")

    assert x is not None
    assert list(x.columns) == feature_columns(6)
    assert x.iloc[0]["lag_1"] == series.prices[-1]
    assert x.iloc[0]["month"] == 4
    assert x.iloc[0]["quarter"] == 2


def test_inference_row_none_when_history_short():
    series = build_region_series(_make_rows(4))[0]
    assert build_inference_row(series, n_lags=6, target_month="2020-05") is None
