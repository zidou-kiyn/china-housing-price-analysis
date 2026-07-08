"""跨源数据质量审计：重叠比值离群、方向一致性、覆盖新鲜度、模型新鲜度。

报告即时计算（全库快照 + 指数 + 全量训练集指纹重算，秒级）；**不加缓存**——
admin 专用低频端点，且「重训后新鲜度徽标必须立刻翻转」是验收语义，TTL 缓存
会在导入/重训后的短窗内给出误导结论。

核心计算全部是纯函数（输入行字典清单），DB/模型读取只发生在 build_report；
方向口径：涨/跌/平三分，|Δ| < FLAT_THRESHOLD_PCT 记"平"——**含平的对比对
不计入一致率分母**（指数在横盘期大量报 100.0，计入会稀释一致率的判别力）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.source_policy import SOURCE_META, source_priority, training_rows_only
from app.ml.dataset import build_multi_source_series
from app.ml.train import ModelStore
from app.models.city import City
from app.models.district import District
from app.services.price_select import select_index_snapshots, select_source_snapshots

# 审计阈值（初始常量，集中定义可调）
RATIO_MIN = 0.5           # 多源重叠比值合理域下界
RATIO_MAX = 2.0           # 多源重叠比值合理域上界
OUTLIERS_CAP = 100        # 离群清单条数上限（防爆，总数另计）
FLAT_THRESHOLD_PCT = 0.1  # |环比/同比| < 0.1% 记"平"

NO_INDEX_STATUS = "no index data"
FLAT_NOTE = "方向=涨/跌/平（|Δ|<0.1% 记平）；任一方为平的对比对不计入一致率分母"


# ---------------------------------------------------------------- 纯函数计算


def _direction(pct: float) -> int:
    """百分比变化 → 方向：+1 涨 / -1 跌 / 0 平（|Δ| < FLAT_THRESHOLD_PCT）。"""
    if abs(pct) < FLAT_THRESHOLD_PCT:
        return 0
    return 1 if pct > 0 else -1


def _is_adjacent_month(prev: str, cur: str) -> bool:
    py, pm = int(prev[:4]), int(prev[5:7])
    cy, cm = int(cur[:4]), int(cur[5:7])
    return (cy * 12 + cm) - (py * 12 + pm) == 1


def compute_overlap_outliers(rows_by_source: dict[str, list[dict]]) -> dict:
    """多源重叠 (region, month) 的两两比值分布与离群清单。

    比值 = 高优先级源价 / 低优先级源价；超出 [RATIO_MIN, RATIO_MAX] 记离群。
    清单按偏离程度降序、截断 OUTLIERS_CAP 条（outliers_total 保留全量计数）。
    """
    by_key: dict[tuple, dict[str, float]] = {}
    for source, rows in rows_by_source.items():
        for r in rows:
            if r.get("supply_price") is None:
                continue
            key = (r["region_type"], r["region_id"], r["year_month"])
            by_key.setdefault(key, {})[source] = float(r["supply_price"])

    pairs = 0
    ratios: list[float] = []
    outliers: list[dict] = []
    for (region_type, region_id, year_month), per_source in by_key.items():
        if len(per_source) < 2:
            continue
        sources = sorted(per_source, key=source_priority)
        for a, b in combinations(sources, 2):
            if per_source[b] <= 0:
                continue
            ratio = per_source[a] / per_source[b]
            pairs += 1
            ratios.append(ratio)
            if not RATIO_MIN <= ratio <= RATIO_MAX:
                outliers.append(
                    {
                        "region_type": region_type,
                        "region_id": region_id,
                        "year_month": year_month,
                        "source_a": a,
                        "price_a": per_source[a],
                        "source_b": b,
                        "price_b": per_source[b],
                        "ratio": round(ratio, 3),
                    }
                )

    outliers.sort(key=lambda o: max(o["ratio"], 1 / o["ratio"]), reverse=True)
    return {
        "pairs": pairs,
        "outliers_total": len(outliers),
        "outliers": outliers[:OUTLIERS_CAP],
        "ratio_median": round(median(ratios), 3) if ratios else None,
    }


def compute_mom_direction_consistency(
    price_rows: list[dict], index_rows: list[dict]
) -> dict:
    """月度价格环比方向 vs 指数环比方向的一致率（同区域同月）。

    price_rows: [{region_id, year_month, supply_price}]（城市级月度源）；
    index_rows: [{region_id, year_month, index_value}]（环比指数，上月=100，
    偏离 100 的点数即环比百分比）。只比较价格序列中相邻自然月且当月有指数
    的对；平的处理见 FLAT_NOTE。
    """
    if not index_rows:
        return {"status": NO_INDEX_STATUS}

    index_map: dict[int, dict[str, float]] = {}
    for r in index_rows:
        index_map.setdefault(r["region_id"], {})[r["year_month"]] = float(r["index_value"])
    series: dict[int, dict[str, float]] = {}
    for r in price_rows:
        if r.get("supply_price") is None:
            continue
        series.setdefault(r["region_id"], {})[r["year_month"]] = float(r["supply_price"])

    regions: set[int] = set()
    compared = matches = flat_excluded = 0
    for region_id, months in series.items():
        idx = index_map.get(region_id)
        if not idx:
            continue
        sorted_months = sorted(months)
        for prev, cur in zip(sorted_months, sorted_months[1:]):
            if not _is_adjacent_month(prev, cur) or cur not in idx or months[prev] <= 0:
                continue
            regions.add(region_id)
            dir_price = _direction((months[cur] - months[prev]) / months[prev] * 100)
            dir_index = _direction(idx[cur] - 100.0)
            if dir_price == 0 or dir_index == 0:
                flat_excluded += 1
                continue
            compared += 1
            if dir_price == dir_index:
                matches += 1

    if not regions:
        return {"status": "no overlap", "note": FLAT_NOTE}
    return {
        "status": "ok",
        "regions": len(regions),
        "compared": compared,
        "matches": matches,
        "agreement_rate": round(matches / compared * 100, 1) if compared else None,
        "flat_excluded": flat_excluded,
        "note": FLAT_NOTE,
    }


def compute_yoy_direction_consistency(
    annual_rows: list[dict], index_rows: list[dict]
) -> dict:
    """年度挂牌同比方向 vs 指数 12 月链乘同比方向的一致率。

    annual_rows: [{region_id, year_month="YYYY-12", supply_price}]；同区域相邻
    两年都有值才构成对。指数同比 = ∏(当年 1~12 月环比指数/100) - 1，12 个月
    任一缺失该对跳过（skipped_missing_index 计数）。
    """
    if not index_rows:
        return {"status": NO_INDEX_STATUS}

    index_map: dict[int, dict[str, float]] = {}
    for r in index_rows:
        index_map.setdefault(r["region_id"], {})[r["year_month"]] = float(r["index_value"])
    annual: dict[int, dict[int, float]] = {}
    for r in annual_rows:
        if r.get("supply_price") is None:
            continue
        annual.setdefault(r["region_id"], {})[int(r["year_month"][:4])] = float(
            r["supply_price"]
        )

    regions: set[int] = set()
    compared = matches = flat_excluded = skipped_missing = 0
    for region_id, years in annual.items():
        idx = index_map.get(region_id)
        if not idx:
            continue
        for year in sorted(years):
            prev_price = years.get(year - 1)
            if prev_price is None or prev_price <= 0:
                continue
            chain = 1.0
            complete = True
            for month in range(1, 13):
                value = idx.get(f"{year:04d}-{month:02d}")
                if value is None or value <= 0:
                    complete = False
                    break
                chain *= value / 100.0
            if not complete:
                skipped_missing += 1
                continue
            regions.add(region_id)
            dir_annual = _direction((years[year] - prev_price) / prev_price * 100)
            dir_index = _direction((chain - 1.0) * 100)
            if dir_annual == 0 or dir_index == 0:
                flat_excluded += 1
                continue
            compared += 1
            if dir_annual == dir_index:
                matches += 1

    if not regions and not skipped_missing:
        return {"status": "no overlap", "note": FLAT_NOTE}
    return {
        "status": "ok",
        "regions": len(regions),
        "compared": compared,
        "matches": matches,
        "agreement_rate": round(matches / compared * 100, 1) if compared else None,
        "flat_excluded": flat_excluded,
        "skipped_missing_index": skipped_missing,
        "note": FLAT_NOTE,
    }


def compute_coverage(
    rows_by_source: dict[str, list[dict]],
    index_rows: list[dict],
    now: datetime,
) -> list[dict]:
    """各源覆盖/新鲜度：区域数、行数、最新月、距今月数（指数源单列 kind=index）。"""
    now_total = now.year * 12 + now.month

    def months_behind(latest: str) -> int:
        return max(0, now_total - (int(latest[:4]) * 12 + int(latest[5:7])))

    entries: list[dict] = []
    for source in sorted(rows_by_source, key=source_priority):
        rows = rows_by_source[source]
        if not rows:
            continue
        latest = max(r["year_month"] for r in rows)
        meta = SOURCE_META.get(source, {})
        entries.append(
            {
                "source": source,
                "kind": "snapshot",
                "granularity": meta.get("granularity"),
                "basis": meta.get("basis"),
                "regions": len({(r["region_type"], r["region_id"]) for r in rows}),
                "rows": len(rows),
                "latest_month": latest,
                "months_behind": months_behind(latest),
            }
        )
    if index_rows:
        latest = max(r["year_month"] for r in index_rows)
        entries.append(
            {
                "source": index_rows[0].get("source") or "index",
                "kind": "index",
                "granularity": "monthly",
                "basis": None,
                "regions": len({r["region_id"] for r in index_rows}),
                "rows": len(index_rows),
                "latest_month": latest,
                "months_behind": months_behind(latest),
            }
        )
    return entries


def compute_model_freshness(active_meta: dict | None, data_fingerprint: str | None) -> dict:
    """活跃模型训练数据指纹 vs 当前库指纹：fresh / stale / unknown。"""
    if active_meta is None:
        return {"status": "unknown", "note": "无活跃模型"}
    base = {
        "model_name": active_meta.get("model_name"),
        "model_version": active_meta.get("version"),
        "trained_at": active_meta.get("trained_at"),
    }
    model_fp = (active_meta.get("dataset") or {}).get("fingerprint")
    if not model_fp:
        return {
            "status": "unknown",
            **base,
            "note": "活跃模型 meta 无 dataset.fingerprint（多源构建器之前的旧版本）",
        }
    if not data_fingerprint:
        return {"status": "unknown", **base, "model_fingerprint": model_fp,
                "note": "当前库无可构建的训练序列"}
    fresh = model_fp == data_fingerprint
    return {
        "status": "fresh" if fresh else "stale",
        **base,
        "model_fingerprint": model_fp,
        "data_fingerprint": data_fingerprint,
        "note": "模型与当前库数据一致" if fresh else "库数据已变化，建议重训",
    }


# ---------------------------------------------------------------- DB 编排


async def _load_source_rows(
    session: AsyncSession,
    region_type: str | None = None,
    region_ids: list[int] | None = None,
) -> dict[str, list[dict]]:
    by_source = await select_source_snapshots(session, region_type, region_ids)
    return {
        source: [
            {
                "region_type": s.region_type,
                "region_id": s.region_id,
                "year_month": s.year_month,
                "supply_price": s.supply_price,
            }
            for s in snaps
        ]
        for source, snaps in by_source.items()
    }


async def _load_index_rows(
    session: AsyncSession,
    region_type: str | None = None,
    region_ids: list[int] | None = None,
) -> list[dict]:
    snaps = await select_index_snapshots(session, region_type, region_ids)
    return [
        {
            "region_type": s.region_type,
            "region_id": s.region_id,
            "year_month": s.year_month,
            "index_value": s.index_value,
            "source": s.source,
        }
        for s in snaps
    ]


async def _compute_data_fingerprint(session: AsyncSession, active_meta: dict) -> str | None:
    """按与训练完全相同的构建器与范围重算当前库指纹。

    范围复刻训练端点（city_codes → 该城市的区县集）；ratio_curve 用活跃模型
    meta["dataset"]["ratio_curve"] override——数据未变时估计曲线与存储曲线相同，
    override 保证比较隔离的是「数据变化」而非曲线重估的扰动。
    """
    region_type: str | None = None
    region_ids: list[int] | None = None
    city_codes = active_meta.get("city_codes") or []
    if city_codes:
        city_ids = list(
            (
                await session.execute(select(City.id).where(City.code.in_(city_codes)))
            ).scalars()
        )
        region_ids = list(
            (
                await session.execute(
                    select(District.id).where(District.city_id.in_(city_ids))
                )
            ).scalars()
        )
        region_type = "district"
        if not region_ids:
            return None

    # 指纹口径必须与训练一致：训练走白名单（creprice-only），指纹重算同样只喂
    # 白名单源，否则库里多源数据会让指纹恒不一致、新鲜度永远 stale。
    rows_by_source = training_rows_only(
        await _load_source_rows(session, region_type, region_ids)
    )
    index_rows = await _load_index_rows(session, region_type, region_ids)
    if not any(rows_by_source.values()):
        return None
    ratio_curve = (active_meta.get("dataset") or {}).get("ratio_curve")
    _, dataset_meta = build_multi_source_series(
        rows_by_source, ratio_curve_override=ratio_curve, index_rows=index_rows
    )
    return dataset_meta.fingerprint


async def _attach_region_names(session: AsyncSession, outliers: list[dict]) -> None:
    """为离群清单补 region_name（仅 cap 后的短清单，两次 IN 查询）。"""
    city_ids = {o["region_id"] for o in outliers if o["region_type"] == "city"}
    dist_ids = {o["region_id"] for o in outliers if o["region_type"] == "district"}
    names: dict[tuple[str, int], str] = {}
    if city_ids:
        for cid, name in (
            await session.execute(select(City.id, City.name).where(City.id.in_(city_ids)))
        ).all():
            names[("city", cid)] = name
    if dist_ids:
        for did, name in (
            await session.execute(
                select(District.id, District.name).where(District.id.in_(dist_ids))
            )
        ).all():
            names[("district", did)] = name
    for o in outliers:
        o["region_name"] = names.get((o["region_type"], o["region_id"]))


async def build_report(session: AsyncSession, store: ModelStore) -> dict:
    """产出完整数据质量报告（四节 + 模型新鲜度），dict 形状与 schema 对齐。"""
    rows_by_source = await _load_source_rows(session)
    index_rows = await _load_index_rows(session)

    overlap = compute_overlap_outliers(rows_by_source)
    await _attach_region_names(session, overlap["outliers"])

    creprice_city = [
        r for r in rows_by_source.get("creprice", []) if r["region_type"] == "city"
    ]
    annual58_city = [
        r
        for r in rows_by_source.get("listing_annual_58", [])
        if r["region_type"] == "city"
    ]

    loaded = store.load_active()
    active_meta = loaded[1] if loaded is not None else None
    data_fingerprint = None
    if active_meta is not None and (active_meta.get("dataset") or {}).get("fingerprint"):
        data_fingerprint = await _compute_data_fingerprint(session, active_meta)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overlap_ratio": overlap,
        "creprice_vs_index": compute_mom_direction_consistency(creprice_city, index_rows),
        "annual_vs_index": compute_yoy_direction_consistency(annual58_city, index_rows),
        "coverage": compute_coverage(rows_by_source, index_rows, datetime.now()),
        "model_freshness": compute_model_freshness(active_meta, data_fingerprint),
    }
