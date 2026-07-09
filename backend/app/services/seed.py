"""启动时种子数据加载：city 表为空则导入 cities.json；价格 seed 按版本增量补缺。"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from itertools import islice
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import flush_all_api_caches, redis_client
from app.core.database import async_session_factory
from app.models.city import City
from app.models.district import District
from app.models.price_distribution import PriceDistribution
from app.models.price_snapshot import PriceSnapshot
from app.pipeline.cleaners import clean_price_distribution, clean_price_timeline
from app.pipeline.snapshot_validator import validate_snapshot_records
from app.services.app_settings import get_setting, set_setting

logger = logging.getLogger(__name__)

_SEED_FILE = Path(__file__).resolve().parent.parent.parent / "seed" / "cities.json"
_PRICE_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed" / "prices"

PRICE_SEED_VERSION_KEY = "seed_price_version"
_PRICE_SEED_SOURCE = "creprice"
_INSERT_CHUNK = 500


async def seed_cities_if_empty() -> None:
    async with async_session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(City))
        if count:
            return

        if not _SEED_FILE.exists():
            logger.warning("Seed file not found: %s", _SEED_FILE)
            return

        cities = json.loads(_SEED_FILE.read_text(encoding="utf-8"))
        await session.execute(
            insert(City),
            [
                {
                    "name": c["name"],
                    "code": c["code"],
                    "province": c.get("province"),
                    "adcode": c.get("adcode"),
                }
                for c in cities
            ],
        )
        await session.commit()
        logger.info("Seeded %d cities from %s", len(cities), _SEED_FILE.name)


# -- 价格 seed 加载 -----------------------------------------------------------


def _compute_price_seed_version() -> str | None:
    """基于 seed/prices/ 下所有文件 mtime 最大值 + 文件数生成版本串；无文件返回 None。"""
    if not _PRICE_SEED_DIR.is_dir():
        return None
    files = list(_PRICE_SEED_DIR.glob("*.json"))
    if not files:
        return None
    latest = max(f.stat().st_mtime for f in files)
    return f"{len(files)}:{latest:.0f}"


def _chunked(rows: list[dict], size: int = _INSERT_CHUNK) -> Iterable[list[dict]]:
    it = iter(rows)
    while chunk := list(islice(it, size)):
        yield chunk


async def _insert_ignore(
    session: AsyncSession,
    model: type,
    rows: list[dict],
    *,
    index_elements: list[str] | None = None,
    constraint: str | None = None,
) -> None:
    """批量 INSERT ... ON CONFLICT DO NOTHING（分块），只补缺不覆盖。"""
    for chunk in _chunked(rows):
        stmt = pg_insert(model).values(chunk)
        if constraint is not None:
            stmt = stmt.on_conflict_do_nothing(constraint=constraint)
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=index_elements)
        await session.execute(stmt)


def _snapshot_rows(
    records: list[dict], region_type: str, region_id: int
) -> list[dict]:
    cleaned = clean_price_timeline(records)
    accepted = validate_snapshot_records(cleaned).accepted
    return [
        {
            "region_type": region_type,
            "region_id": region_id,
            "year_month": r["year_month"],
            "supply_price": r.get("supply_price"),
            "attention_price": r.get("attention_price"),
            "value_price": r.get("value_price"),
            "sample_count": r.get("sample_count"),
            "source": _PRICE_SEED_SOURCE,
        }
        for r in accepted
    ]


def _distribution_rows(
    records: list[dict], region_type: str, region_id: int, year_month: str
) -> list[dict]:
    cleaned = clean_price_distribution(records, year_month)
    return [
        {
            "region_type": region_type,
            "region_id": region_id,
            "year_month": r["year_month"],
            "price_range_low": r["price_range_low"],
            "price_range_high": r["price_range_high"],
            "percentage": (
                Decimal(str(r["percentage"])) if r.get("percentage") is not None else None
            ),
        }
        for r in cleaned
    ]


async def seed_prices_if_needed(session: AsyncSession) -> None:
    """按 seed 版本增量加载价格数据：区县→时序→分布，全程 ON CONFLICT DO NOTHING。

    仅在 seed/prices/ 版本变化时执行；已有数据（含真实采集）永不被 seed 覆盖。
    """
    version = _compute_price_seed_version()
    if version is None:
        logger.info("无价格 seed 文件，跳过加载")
        return

    stored = await get_setting(session, PRICE_SEED_VERSION_KEY)
    if stored and stored.get("version") == version:
        return

    city_map: dict[str, int] = dict(
        (await session.execute(select(City.code, City.id))).all()
    )

    files = sorted(_PRICE_SEED_DIR.glob("*.json"))
    # 第一遍：插入全部区县，建立 (city_id, code) → id 映射（唯一键为 city_id+code 复合）。
    parsed: list[tuple[dict, int]] = []
    district_rows: list[dict] = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        city_id = city_map.get(data.get("city_code"))
        if city_id is None:
            logger.warning("seed 城市 %s 不在 city 表，跳过", data.get("city_code"))
            continue
        parsed.append((data, city_id))
        for d in data.get("districts", []):
            district_rows.append(
                {"name": d["name"], "code": d["code"], "city_id": city_id}
            )

    await _insert_ignore(
        session, District, district_rows, constraint="uq_district_city_code"
    )
    await session.flush()

    # (city_id, code) → district_id：短码在不同城市重复（"高新区/经开区/丰泽区"等），
    # 只按 code 反查会拿到别城的 district_id，导致 snapshot 落到错的行政区。
    dist_codes = list({row["code"] for row in district_rows})
    dist_map: dict[tuple[int, str], int] = {}
    for chunk in _chunked([{"code": c} for c in dist_codes]):
        codes = [c["code"] for c in chunk]
        result = await session.execute(
            select(District.city_id, District.code, District.id).where(
                District.code.in_(codes)
            )
        )
        for city_id_, code_, dist_id_ in result.all():
            dist_map[(city_id_, code_)] = dist_id_

    # 第二遍：逐城市加载时序与分布（按城市分块，控制内存）。
    total_snap = 0
    total_dist = 0
    for data, city_id in parsed:
        year_month = str(data.get("scraped_at", ""))[:7]
        timeline = data.get("price_timeline", {})
        distribution = data.get("price_distribution", {})

        snap_rows = _snapshot_rows(timeline.get("city", []), "city", city_id)
        dist_rows = _distribution_rows(
            distribution.get("city", []), "city", city_id, year_month
        )
        for dist_code, records in timeline.get("districts", {}).items():
            dist_id = dist_map.get((city_id, dist_code))
            if dist_id is None:
                continue
            snap_rows.extend(_snapshot_rows(records, "district", dist_id))
        for dist_code, records in distribution.get("districts", {}).items():
            dist_id = dist_map.get((city_id, dist_code))
            if dist_id is None:
                continue
            dist_rows.extend(
                _distribution_rows(records, "district", dist_id, year_month)
            )

        await _insert_ignore(
            session,
            PriceSnapshot,
            snap_rows,
            constraint="uq_price_snapshot_region_month_source",
        )
        await _insert_ignore(
            session,
            PriceDistribution,
            dist_rows,
            constraint="uq_price_distribution_region_range",
        )
        total_snap += len(snap_rows)
        total_dist += len(dist_rows)

    await set_setting(session, PRICE_SEED_VERSION_KEY, {"version": version})
    logger.info(
        "价格 seed 加载完成 v%s：%d 城市，%d 时序行，%d 分布行",
        version,
        len(parsed),
        total_snap,
        total_dist,
    )
    # 全站数据刚变更，抹掉所有 api:* 缓存，避免下次请求读到旧 region 结构。
    dropped = await flush_all_api_caches(redis_client)
    if dropped:
        logger.info("seed 后清除 %d 个 api 缓存 key", dropped)
