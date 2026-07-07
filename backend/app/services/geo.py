"""GeoJSON 服务：DataV 边界下载、adcode 回填、落盘与读取。

数据源为阿里 DataV.GeoAtlas 的 <adcode>_full.json（含区县子区域，非官方接口无 SLA）。
文件落盘到仓库根 data/geo/（容器内 /data/geo），由 GET /api/v1/geo/{city_code} 提供，
前端地图组件经 API 加载，管理端爬图后无需重新构建前端。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collector.storage import DEFAULT_DATA_ROOT
from app.core.config import settings
from app.models.city import City

logger = logging.getLogger(__name__)

DATAV_URL = "https://geo.datav.aliyun.com/areas_v3/bound/{adcode}_full.json"
CHINA_ADCODE = "100000"
# 省间遍历/逐城下载的固定间隔，控制 DataV 请求频率
REQUEST_INTERVAL = 0.2


def geo_root() -> Path:
    """GeoJSON 落盘目录：默认仓库根 data/geo/（容器内 /data/geo），可经配置覆盖。"""
    root = Path(settings.geo_dir) if settings.geo_dir else DEFAULT_DATA_ROOT / "geo"
    root.mkdir(parents=True, exist_ok=True)
    return root


def geo_path(city_code: str) -> Path:
    return geo_root() / f"{city_code}.json"


def list_available() -> set[str]:
    """扫描 geo 目录，返回已有地图的城市 code 集合。"""
    return {p.stem for p in geo_root().glob("*.json")}


async def fetch_geojson(client: httpx.AsyncClient, adcode: str) -> dict | None:
    resp = await client.get(DATAV_URL.format(adcode=adcode))
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data if data.get("features") else None


async def build_city_index(client: httpx.AsyncClient) -> dict[str, str]:
    """遍历各省构建 城市名→adcode 索引（约 35 次请求，调用方应只构建一次）。"""
    index: dict[str, str] = {}
    china = await fetch_geojson(client, CHINA_ADCODE)
    if china is None:
        return index
    for prov in china["features"]:
        props = prov["properties"]
        index.setdefault(props["name"], str(props["adcode"]))  # 直辖市即城市本身
        prov_data = await fetch_geojson(client, str(props["adcode"]))
        if prov_data is None:
            continue
        for feat in prov_data["features"]:
            fp = feat["properties"]
            if fp.get("name"):
                index.setdefault(fp["name"], str(fp["adcode"]))
        await asyncio.sleep(REQUEST_INTERVAL)
    return index


def match_adcode(index: dict[str, str], city_name: str) -> str | None:
    """先精确匹配「名/名+市」，再前缀匹配（如 黔东南→黔东南苗族侗族自治州），歧义视为未命中。"""
    for key in (city_name, f"{city_name}市"):
        if key in index:
            return index[key]
    prefixed = [adcode for name, adcode in index.items() if name.startswith(city_name)]
    return prefixed[0] if len(prefixed) == 1 else None


async def backfill_adcodes(session: AsyncSession, client: httpx.AsyncClient) -> int:
    """为 city 表中所有缺 adcode 的城市在线检索并回填（索引构建一次、全表覆盖）。"""
    missing = (
        (await session.execute(select(City).where(City.adcode.is_(None)))).scalars().all()
    )
    if not missing:
        return 0

    logger.info("构建全国 城市名→adcode 索引（约 35 次请求）…")
    index = await build_city_index(client)
    filled = 0
    for city in missing:
        adcode = match_adcode(index, city.name)
        if adcode:
            city.adcode = adcode
            filled += 1
    await session.commit()
    logger.info("adcode 回填完成: %d/%d", filled, len(missing))
    return filled


async def fetch_city_geo(client: httpx.AsyncClient, city: City) -> dict:
    """下载单城市边界并落盘，返回摘要 {"districts": n}；失败抛异常。"""
    if not city.adcode:
        raise ValueError(f"城市 {city.name}({city.code}) 无 adcode，DataV 未收录或名称未匹配")

    geo = await fetch_geojson(client, city.adcode)
    if geo is None:
        raise ValueError(f"下载 adcode={city.adcode} 边界失败或无 features")

    geo_path(city.code).write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    return {"districts": len(geo["features"])}
