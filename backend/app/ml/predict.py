"""滚动多步预测与置信区间（docs/06 §7）。"""

from dataclasses import dataclass

import numpy as np

from app.ml.features import RegionSeries, build_inference_row, shift_month

MIN_HISTORY_MONTHS = 12


@dataclass
class PredictionPoint:
    target_month: str
    predicted_price: int
    confidence_lower: int
    confidence_upper: int


def rolling_predict(
    model, meta: dict, region_series: RegionSeries, months_ahead: int = 3
) -> list[PredictionPoint]:
    """逐月滚动预测：预测值回填序列作为后续步骤的 lag 输入。

    置信区间按 meta["ci_strategy"] 分派：
    per_tree（RF）取各棵树预测的 均值 ± 1.96×标准差；
    residual（XGBoost）取 预测值 ± 1.96×meta["resid_std"]。
    历史不足 MIN_HISTORY_MONTHS 或不足模型 lag 窗口时抛 ValueError。
    """
    if len(region_series.prices) < MIN_HISTORY_MONTHS:
        raise ValueError(f"历史数据不足 {MIN_HISTORY_MONTHS} 个月，无法预测")

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
            margin = 1.96 * float(meta["resid_std"])

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

    return points
