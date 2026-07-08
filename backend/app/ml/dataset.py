"""多源训练集构建器：分源快照行 → 校准/扩充后的 RegionSeries + DatasetMeta。

职责边界：本模块只做「DB 快照行（分源）→ 序列」；features.py 只做「序列 →
特征矩阵」；train.py 只做训练。源的粒度/口径一律取 source_policy.SOURCE_META
（唯一定义处），禁止在 ML 层硬编码源名清单。

口径校准用逐年分段比值（北京双口径重叠期实证：比值 0.79→1.09 漂移，
单一全局折价系数不成立）。年度挂牌点校准后线性插值成月序列，全部标记
is_annual_interp 并按 ANNUAL_SAMPLE_WEIGHT 降权——12 月真实点亦是年度挂牌
口径而非月度行情，不降权会让 330 城年度样本淹没真实月度样本。
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from statistics import median

import pandas as pd

from app.core.source_policy import SOURCE_META, source_priority
from app.ml.features import RegionSeries, build_region_series, shift_month

# 年度插值样本权重（真实月度=1.0）。置 0 即退化回纯月度训练集（回滚开关）。
ANNUAL_SAMPLE_WEIGHT = 0.3

# 未登记 SOURCE_META 的源按默认口径处理（与读取层兜底约定一致）
_DEFAULT_SOURCE_META = {"granularity": "monthly", "basis": "listing"}

RegionKey = tuple[str, int]  # (region_type, region_id)


@dataclass
class DatasetMeta:
    """训练集指纹：各源分布、校准曲线与数据指纹（写入模型 meta 供追溯）。"""

    per_source: dict[str, dict]  # {source: {rows, regions, min_month, max_month}}
    ratio_curve: dict[str, float]  # {year: 成交/挂牌 比值}
    ratio_pairs: int  # 重叠对样本数
    calibrated_rows: int  # 应用了校准的年度行数
    fingerprint: str  # sha256(排序后 region:month:price)[:16]

    def to_dict(self) -> dict:
        return asdict(self)


def _source_meta(source: str) -> dict[str, str]:
    return SOURCE_META.get(source, _DEFAULT_SOURCE_META)


def _month_range(start: str, end: str) -> list[str]:
    months = []
    m = start
    while m <= end:
        months.append(m)
        m = shift_month(m, 1)
    return months


def estimate_basis_ratio_curve(
    rows_by_source: dict[str, list[dict]],
) -> tuple[dict[str, float], int]:
    """双口径重叠对 → 逐年「成交/挂牌」比值曲线。

    对 = 同 (region_type, region_id, year_month) 且一边来自月度成交源、另一边
    来自年度挂牌源；按年份聚合 median(transaction / listing)。同键多源时取
    高优先级源的值。返回 (曲线 {year: ratio}, 重叠对数)；无重叠对时曲线为空。
    """
    transaction_vals: dict[tuple, tuple[int, float]] = {}
    listing_vals: dict[tuple, tuple[int, float]] = {}
    for source, rows in rows_by_source.items():
        meta = _source_meta(source)
        if meta["granularity"] == "monthly" and meta["basis"] == "transaction":
            bucket = transaction_vals
        elif meta["granularity"] == "annual" and meta["basis"] == "listing":
            bucket = listing_vals
        else:
            continue
        prio = source_priority(source)
        for r in rows:
            if r.get("supply_price") is None:
                continue
            key = (r["region_type"], r["region_id"], r["year_month"])
            if key not in bucket or prio < bucket[key][0]:
                bucket[key] = (prio, float(r["supply_price"]))

    per_year: dict[str, list[float]] = {}
    pairs = 0
    for key, (_, t_val) in transaction_vals.items():
        hit = listing_vals.get(key)
        if hit is None or hit[1] <= 0:
            continue
        pairs += 1
        per_year.setdefault(key[2][:4], []).append(t_val / hit[1])
    curve = {year: round(median(vals), 4) for year, vals in sorted(per_year.items())}
    return curve, pairs


def _ratio_for_year(ratio_curve: dict[str, float], year: str) -> float:
    """年份不在曲线内时沿用最近年份的比值（重叠期外取最近端点年）。"""
    if not ratio_curve:
        return 1.0
    if year in ratio_curve:
        return ratio_curve[year]
    nearest = min(ratio_curve, key=lambda y: (abs(int(y) - int(year)), y))
    return ratio_curve[nearest]


def _annual_to_monthly(
    rows: list[dict], ratio_curve: dict[str, float], basis: str = "listing"
) -> tuple[list[RegionSeries], int]:
    """年度 12 月点：逐年比值校准 → 点间线性插值为连续月序列。

    全部点 interp_flags=1（12 月真实点亦是年度口径，非月度行情）、权重
    ANNUAL_SAMPLE_WEIGHT；首点前/末点后不外推。返回 (序列列表, 校准行数)。
    """
    result: list[RegionSeries] = []
    calibrated = 0
    df = pd.DataFrame([r for r in rows if r.get("supply_price") is not None])
    if df.empty:
        return result, calibrated
    for (region_type, region_id), group in df.groupby(["region_type", "region_id"]):
        group = group.sort_values("year_month")
        points: dict[str, float] = {}
        for ym, price in zip(group["year_month"], group["supply_price"]):
            points[ym] = float(price) * _ratio_for_year(ratio_curve, ym[:4])
            if ratio_curve:
                calibrated += 1
        full_months = _month_range(min(points), max(points))
        series = pd.Series([points.get(m) for m in full_months], dtype=float).interpolate(
            method="linear"
        )
        result.append(
            RegionSeries(
                region_type=str(region_type),
                region_id=int(region_id),
                months=full_months,
                prices=series.tolist(),
                basis=basis,
                weights=[ANNUAL_SAMPLE_WEIGHT] * len(full_months),
                interp_flags=[1] * len(full_months),
            )
        )
    return result, calibrated


def _merge_region(
    key: RegionKey,
    monthly: list[tuple[int, RegionSeries]],
    annual: list[tuple[int, RegionSeries]],
) -> RegionSeries:
    """同区域多源序列合并：真实月度 > 年度插值 > 缺口线性插值（flag=1、降权）。

    同月多源竞争按 (月度优先, 源优先级) 取一值，月份不重复；月份连续性由
    各源月份并集重建，仍缺的中间月线性插值并降权。
    """
    # month -> (rank, price, weight, flag)；rank 小者胜
    claims: dict[str, tuple[tuple[int, int], float, float, int]] = {}
    for tier, group in ((0, monthly), (1, annual)):
        for prio, rs in group:
            rank = (tier, prio)
            for i, month in enumerate(rs.months):
                cur = claims.get(month)
                if cur is None or rank < cur[0]:
                    claims[month] = (
                        rank,
                        rs.prices[i],
                        rs.weights[i] if rs.weights else 1.0,
                        rs.interp_flags[i] if rs.interp_flags else 0,
                    )

    full_months = _month_range(min(claims), max(claims))
    prices = pd.Series(
        [claims[m][1] if m in claims else None for m in full_months], dtype=float
    ).interpolate(method="linear")
    weights = [claims[m][2] if m in claims else ANNUAL_SAMPLE_WEIGHT for m in full_months]
    flags = [claims[m][3] if m in claims else 1 for m in full_months]

    if monthly:
        # 真实月度点最多的月度源决定序列口径（并列取高优先级源）
        basis = min(monthly, key=lambda pr: (-len(pr[1].months), pr[0]))[1].basis
    else:
        basis = min(annual, key=lambda pr: pr[0])[1].basis

    return RegionSeries(
        region_type=key[0],
        region_id=key[1],
        months=full_months,
        prices=prices.tolist(),
        basis=basis,
        weights=weights,
        interp_flags=flags,
    )


def _fingerprint(series_list: list[RegionSeries]) -> str:
    """sha256(排序后 region:month:price 拼接) 前 16 位，标识训练数据内容。"""
    parts = sorted(
        f"{rs.region_type}:{rs.region_id}:{m}:{p:.2f}"
        for rs in series_list
        for m, p in zip(rs.months, rs.prices)
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def build_multi_source_series(
    rows_by_source: dict[str, list[dict]],
    ratio_curve_override: dict[str, float] | None = None,
) -> tuple[list[RegionSeries], DatasetMeta]:
    """月度/年度分源构建 + 合并去重（真实月度优先），返回 (序列, DatasetMeta)。

    rows_by_source: {source: [{region_type, region_id, year_month, supply_price}]}。
    月度源沿用 build_region_series 现有逻辑（插值 + 缺失率门槛）；年度源校准后
    插值扩充；同 (region, month) 真实月度值优先，不产生重复行。
    仅有单一月度源且无年度数据的区域原样返回（纯月度路径不回退）。

    ratio_curve_override 供预测路径传入训练时的曲线（模型 meta["dataset"]
    ["ratio_curve"]）：传入即跳过重估——训练/推理校准必须一致，单区域重估
    会产生偏差；空 dict 表示训练时无校准，推理同样不校准。
    """
    cleaned = {
        source: [r for r in rows if r.get("supply_price") is not None]
        for source, rows in rows_by_source.items()
    }
    cleaned = {source: rows for source, rows in cleaned.items() if rows}

    per_source: dict[str, dict] = {}
    for source, rows in sorted(cleaned.items(), key=lambda kv: source_priority(kv[0])):
        months = [r["year_month"] for r in rows]
        per_source[source] = {
            "rows": len(rows),
            "regions": len({(r["region_type"], r["region_id"]) for r in rows}),
            "min_month": min(months),
            "max_month": max(months),
        }

    if ratio_curve_override is not None:
        ratio_curve, ratio_pairs = dict(ratio_curve_override), 0  # 复用外部曲线，不重估
    else:
        ratio_curve, ratio_pairs = estimate_basis_ratio_curve(cleaned)

    monthly_sources = sorted(
        (s for s in cleaned if _source_meta(s)["granularity"] == "monthly"),
        key=source_priority,
    )
    annual_sources = sorted(
        (s for s in cleaned if _source_meta(s)["granularity"] == "annual"),
        key=source_priority,
    )

    # 月度源：逐源沿用现有序列构建（插值 + 缺失率门槛），口径取自源元数据
    monthly_map: dict[RegionKey, list[tuple[int, RegionSeries]]] = {}
    for source in monthly_sources:
        basis = _source_meta(source)["basis"]
        for rs in build_region_series(cleaned[source]):
            rs.basis = basis
            monthly_map.setdefault((rs.region_type, rs.region_id), []).append(
                (source_priority(source), rs)
            )

    # 年度源：跨源行级去重（高优先级先占同 (region, month)）→ 校准 + 插值
    annual_map: dict[RegionKey, list[tuple[int, RegionSeries]]] = {}
    calibrated_rows = 0
    claimed: set[tuple] = set()
    for source in annual_sources:
        meta = _source_meta(source)
        rows = [
            r
            for r in cleaned[source]
            if (r["region_type"], r["region_id"], r["year_month"]) not in claimed
        ]
        claimed.update((r["region_type"], r["region_id"], r["year_month"]) for r in rows)
        # 校准曲线是「挂牌→成交」，只作用于挂牌口径的年度源
        curve = ratio_curve if meta["basis"] == "listing" else {}
        series, calibrated = _annual_to_monthly(rows, curve, basis=meta["basis"])
        calibrated_rows += calibrated
        for rs in series:
            annual_map.setdefault((rs.region_type, rs.region_id), []).append(
                (source_priority(source), rs)
            )

    result: list[RegionSeries] = []
    for key in sorted(set(monthly_map) | set(annual_map)):
        monthly = monthly_map.get(key, [])
        annual = annual_map.get(key, [])
        if not annual and len(monthly) == 1:
            result.append(monthly[0][1])  # 纯月度单源区域：原样保留（回归不变）
        elif not monthly and len(annual) == 1:
            result.append(annual[0][1])
        else:
            result.append(_merge_region(key, monthly, annual))

    dataset_meta = DatasetMeta(
        per_source=per_source,
        ratio_curve=ratio_curve,
        ratio_pairs=ratio_pairs,
        calibrated_rows=calibrated_rows,
        fingerprint=_fingerprint(result),
    )
    return result, dataset_meta
