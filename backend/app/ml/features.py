"""特征工程：price_snapshot 月度序列 → 特征矩阵（docs/06 §3）。

所有滞后/滚动/变化率特征均基于 shift 后序列构造，特征行只含 t-1 及更早的信息，
保证训练无标签泄漏、推理可用「历史 + 已预测值」滚动构造。
"""

from dataclasses import dataclass

import pandas as pd

MAX_MISSING_RATIO = 0.3
REGION_TYPE_ENC = {"city": 0, "district": 1, "area": 2}
BASIS_ENC = {"listing": 0, "transaction": 1}


@dataclass
class RegionSeries:
    """单区域插值后的连续月度价格序列。

    新增字段均带默认值（向后兼容）：weights/interp_flags 为 None 时按
    全 1 权重 / 全 0 标记处理（纯月度真实序列）。
    """

    region_type: str
    region_id: int
    months: list[str]  # 连续 YYYY-MM
    prices: list[float]
    basis: str = "listing"  # listing | transaction（口径，见 source_policy.SOURCE_META）
    weights: list[float] | None = None  # 与 prices 等长；None=全 1
    interp_flags: list[int] | None = None  # 1=年度插值点；None=全 0


def shift_month(year_month: str, delta: int) -> str:
    year, month = map(int, year_month.split("-"))
    total = year * 12 + month - 1 + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def feature_columns(n_lags: int) -> list[str]:
    # 新列只在尾部追加：旧模型 meta.features 不含它们，推理按 meta.features 切片即可兼容
    return (
        [f"lag_{i}" for i in range(1, n_lags + 1)]
        + ["rolling_mean_3", "rolling_mean_6", "rolling_mean_12", "rolling_std_6"]
        + ["mom_pct", "yoy_pct", "month", "quarter", "region_type_enc", "region_id"]
        + ["basis_enc", "is_annual_interp"]
    )


def build_region_series(rows: list[dict]) -> list[RegionSeries]:
    """快照行分组为连续月序列，缺失月线性插值；缺失率 >30% 的区域跳过。

    rows: [{region_type, region_id, year_month, supply_price}]，supply_price 可为 None。
    """
    if not rows:
        return []
    df = pd.DataFrame(rows).dropna(subset=["supply_price"])
    if df.empty:
        return []
    result: list[RegionSeries] = []
    for (region_type, region_id), group in df.groupby(["region_type", "region_id"]):
        group = group.sort_values("year_month")
        months = group["year_month"].tolist()
        full_months = []
        m = months[0]
        while m <= months[-1]:
            full_months.append(m)
            m = shift_month(m, 1)

        series = pd.Series(
            group.set_index("year_month")["supply_price"].astype(float).reindex(full_months)
        )
        missing_ratio = series.isna().mean()
        if missing_ratio > MAX_MISSING_RATIO:
            continue
        series = series.interpolate(method="linear")

        result.append(
            RegionSeries(
                region_type=str(region_type),
                region_id=int(region_id),
                months=full_months,
                prices=series.tolist(),
            )
        )
    return result


def _feature_row(
    history: list[float],
    n_lags: int,
    target_month: str,
    region_type: str,
    region_id: int,
    basis: str = "listing",
    is_annual_interp: int = 0,
) -> dict | None:
    """由 target_month 之前的完整历史构造一行特征；历史不足 n_lags 时返回 None。"""
    if len(history) < n_lags:
        return None

    s = pd.Series(history)
    row: dict = {f"lag_{i}": history[-i] for i in range(1, n_lags + 1)}
    row["rolling_mean_3"] = s.tail(3).mean()
    row["rolling_mean_6"] = s.tail(6).mean()
    row["rolling_mean_12"] = s.tail(12).mean()
    row["rolling_std_6"] = s.tail(6).std() if len(s) >= 2 else 0.0
    prev, prev2 = history[-1], history[-2] if len(history) >= 2 else None
    row["mom_pct"] = (prev - prev2) / prev2 * 100 if prev2 else 0.0
    year_ago = history[-13] if len(history) >= 13 else None
    row["yoy_pct"] = (prev - year_ago) / year_ago * 100 if year_ago else 0.0
    month = int(target_month.split("-")[1])
    row["month"] = month
    row["quarter"] = (month - 1) // 3 + 1
    row["region_type_enc"] = REGION_TYPE_ENC.get(region_type, -1)
    row["region_id"] = region_id
    row["basis_enc"] = BASIS_ENC.get(basis, 0)
    row["is_annual_interp"] = is_annual_interp
    return row


def build_training_frame(series_list: list[RegionSeries], n_lags: int) -> pd.DataFrame:
    """构造训练集：每个 (区域, 月) 一行，特征 + 标签 y + year_month + weight。"""
    rows = []
    for rs in series_list:
        for idx in range(n_lags, len(rs.months)):
            row = _feature_row(
                rs.prices[:idx],
                n_lags,
                rs.months[idx],
                rs.region_type,
                rs.region_id,
                rs.basis,
                rs.interp_flags[idx] if rs.interp_flags else 0,
            )
            if row is None:
                continue
            row["y"] = rs.prices[idx]
            row["year_month"] = rs.months[idx]
            row["weight"] = rs.weights[idx] if rs.weights else 1.0
            rows.append(row)
    frame = pd.DataFrame(rows)
    return frame.sort_values("year_month").reset_index(drop=True) if not frame.empty else frame


def build_inference_row(
    rs: RegionSeries, n_lags: int, target_month: str, columns: list[str] | None = None
) -> pd.DataFrame | None:
    """用全部已知序列（含已回填的预测值）构造 target_month 的单行特征。

    columns 传模型 meta["features"] 可按训练时列切片（旧模型无新列亦兼容）。
    未来月份视为月度行情目标，is_annual_interp 恒为 0。
    """
    row = _feature_row(rs.prices, n_lags, target_month, rs.region_type, rs.region_id, rs.basis, 0)
    if row is None:
        return None
    return pd.DataFrame([row])[columns or feature_columns(n_lags)]
