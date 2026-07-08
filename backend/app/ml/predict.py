"""滚动多步预测与置信区间（docs/06 §7）。"""

from dataclasses import dataclass

import numpy as np

from app.ml.features import RegionSeries, build_inference_row, shift_month

MIN_HISTORY_MONTHS = 12
# 年度插值序列的区间惩罚：插值序列自相关高、真实波动被抹平，区间必然低估。
# 1.5 为保守初值，后续可用回测校准。
ANNUAL_CI_PENALTY = 1.5


@dataclass
class PredictionPoint:
    target_month: str
    predicted_price: int
    confidence_lower: int
    confidence_upper: int


def _data_quality(interp_flags: list[int] | None) -> str:
    """依据序列插值标记判定数据口径：monthly | annual_interp | mixed。

    flags 为 None（纯月度真实序列）视作全 0。
    """
    if not interp_flags or not any(interp_flags):
        return "monthly"
    if all(interp_flags):
        return "annual_interp"
    return "mixed"


def rolling_predict(
    model, meta: dict, region_series: RegionSeries, months_ahead: int = 3
) -> tuple[list[PredictionPoint], str]:
    """逐月滚动预测：预测值回填序列作为后续步骤的 lag 输入。

    返回 (预测点列表, data_quality)。data_quality 由输入序列的 interp_flags
    判定；为 annual_interp 时区间乘 ANNUAL_CI_PENALTY。
    置信区间按 meta["ci_strategy"] 分派：
    per_tree（RF）取各棵树预测的 均值 ± 1.96×标准差；
    residual（XGBoost）优先用相对残差 预测值 ± 1.96×meta["resid_std_pct"]×预测值
    （随价位缩放），旧模型 meta 只有绝对 resid_std 时沿用旧算式。
    历史不足 MIN_HISTORY_MONTHS 或不足模型 lag 窗口时抛 ValueError。
    """
    if len(region_series.prices) < MIN_HISTORY_MONTHS:
        raise ValueError(f"历史数据不足 {MIN_HISTORY_MONTHS} 个月，无法预测")

    data_quality = _data_quality(region_series.interp_flags)
    n_lags = meta["n_lags"]
    series = RegionSeries(
        region_type=region_series.region_type,
        region_id=region_series.region_id,
        months=list(region_series.months),
        prices=list(region_series.prices),
        basis=region_series.basis,
    )

    points: list[PredictionPoint] = []
    for _ in range(months_ahead):
        target_month = shift_month(series.months[-1], 1)
        # 按训练时特征列切片：旧模型 meta.features 不含新列，天然兼容
        x = build_inference_row(series, n_lags, target_month, meta.get("features"))
        if x is None:
            raise ValueError(f"历史数据不足模型窗口 {n_lags} 个月，无法预测")

        if meta.get("ci_strategy", "per_tree") == "per_tree":
            per_tree = np.array([tree.predict(x.to_numpy())[0] for tree in model.estimators_])
            y_hat = float(per_tree.mean())
            margin = 1.96 * float(per_tree.std())
        else:
            y_hat = float(model.predict(x.to_numpy())[0])
            if meta.get("resid_std_pct") is not None:
                # 相对残差随价位缩放，不同价位城市区间均衡
                margin = 1.96 * float(meta["resid_std_pct"]) * abs(y_hat)
            else:
                margin = 1.96 * float(meta["resid_std"])

        if data_quality == "annual_interp":
            margin *= ANNUAL_CI_PENALTY

        points.append(
            PredictionPoint(
                target_month=target_month,
                predicted_price=round(y_hat),
                confidence_lower=round(y_hat - margin),
                confidence_upper=round(y_hat + margin),
            )
        )
        series.months.append(target_month)
        series.prices.append(y_hat)

    return points, data_quality
