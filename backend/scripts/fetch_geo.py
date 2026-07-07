"""补齐前端地图 GeoJSON：下载城市区县边界到 frontend/public/geo/<code>.json。

用法：
    .venv/bin/python scripts/fetch_geo.py              # 补齐所有已采集城市（有 district 数据）的缺图
    .venv/bin/python scripts/fetch_geo.py fz xm        # 指定城市（creprice 代码）
    .venv/bin/python scripts/fetch_geo.py nn=450100    # 未收录城市显式指定国标 adcode

数据源为阿里 DataV.GeoAtlas 的 <adcode>_full.json（含区县子区域，非官方接口无 SLA）。
未显式给 adcode 时先查内置映射，查不到再构建一次 城市名→adcode 全国索引在线检索。
下载后与 district 表比对区县名并打印差异——名字对不上的区县在热力图上不会着色。

生产（Docker）注意：geo 文件在 vite build 时打进前端 nginx 镜像，补完后需重建：
    docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build frontend
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.city import City
from app.models.district import District

GEO_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "geo"
DATAV_URL = "https://geo.datav.aliyun.com/areas_v3/bound/{adcode}_full.json"
CHINA_ADCODE = "100000"

# creprice 城市代码 → 国标 adcode；在线检索命中过的城市可补录进来省去逐省翻找
KNOWN_ADCODES = {"qz": "350500", "fz": "350100", "xm": "350200"}


async def fetch_geojson(client: httpx.AsyncClient, adcode: str) -> dict | None:
    resp = await client.get(DATAV_URL.format(adcode=adcode))
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data if data.get("features") else None


async def build_city_index(client: httpx.AsyncClient) -> dict[str, str]:
    """遍历各省构建 城市名→adcode 索引（约 35 次请求，整个进程只构建一次）。"""
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
        await asyncio.sleep(0.2)  # 控制请求频率，避免被 DataV 限流
    return index


def match_adcode(index: dict[str, str], city_name: str) -> str | None:
    """先精确匹配「名/名+市」，再前缀匹配（如 黔东南→黔东南苗族侗族自治州），歧义视为未命中。"""
    for key in (city_name, f"{city_name}市"):
        if key in index:
            return index[key]
    prefixed = [adcode for name, adcode in index.items() if name.startswith(city_name)]
    return prefixed[0] if len(prefixed) == 1 else None


def report_name_diff(geo_names: set[str], db_names: set[str]) -> None:
    """前端按名字精确匹配着色，两侧名字有出入时需要人工核对。"""
    if not db_names:
        print("提示: 库中该城市暂无区县数据，地图会整片显示「暂无数据」（先跑 run_pipeline 采集）")
        return
    uncolored = sorted(db_names - geo_names)
    no_data = sorted(geo_names - db_names)
    if uncolored:
        print(f"警告: 库中区县在地图上无同名区域（不会着色）: {', '.join(uncolored)}")
    else:
        print("区县名比对通过: 库中区县全部可着色")
    if no_data:
        print(f"提示: 地图区域在库中暂无数据（显示「暂无数据」）: {', '.join(no_data)}")


async def load_district_names(session: AsyncSession, city_id: int) -> set[str]:
    rows = await session.scalars(select(District.name).where(District.city_id == city_id))
    return set(rows.all())


async def main() -> int:
    if any(arg.startswith("-") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    targets: list[tuple[str, str | None]] = []
    for arg in sys.argv[1:]:
        code, _, adcode = arg.partition("=")
        targets.append((code, adcode or None))

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    failed = []
    try:
        async with session_factory() as session:
            cities = {c.code: c for c in (await session.scalars(select(City))).all()}
            if not targets:
                # city 表种子化了全国城市，只有采集过的城市才有 district，也才值得补图
                collected = set(
                    (await session.scalars(select(District.city_id).distinct())).all()
                )
                targets = [
                    (code, None)
                    for code, c in cities.items()
                    if c.id in collected and not (GEO_DIR / f"{code}.json").exists()
                ]
                if not targets:
                    print("所有已采集城市均已有地图文件，无需补图")
                    return 0

            GEO_DIR.mkdir(parents=True, exist_ok=True)
            city_index: dict[str, str] | None = None
            async with httpx.AsyncClient(timeout=30) as client:
                for code, adcode in targets:
                    city = cities.get(code)
                    label = f"{city.name}({code})" if city else code
                    print(f"\n== 补图 {label} ==")

                    out = GEO_DIR / f"{code}.json"
                    if out.exists():
                        print(f"已存在，跳过（需重新下载请先删除 {out}）")
                        continue

                    if adcode is None:
                        adcode = KNOWN_ADCODES.get(code)
                    if adcode is None:
                        if city is None:
                            print(f"失败: city 表中无代码 {code}，请显式指定 {code}=<adcode>")
                            failed.append(code)
                            continue
                        if city_index is None:
                            print("构建全国 城市名→adcode 索引（约 35 次请求）…")
                            city_index = await build_city_index(client)
                        adcode = match_adcode(city_index, city.name)
                    if adcode is None:
                        print(f"失败: 未检索到 adcode，请显式指定 {code}=<adcode>")
                        failed.append(code)
                        continue

                    geo = await fetch_geojson(client, adcode)
                    if geo is None:
                        print(f"失败: 下载 adcode={adcode} 边界失败或文件无 features")
                        failed.append(code)
                        continue

                    out.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
                    geo_names = {f["properties"].get("name", "") for f in geo["features"]}
                    print(f"已写入 {out}（{len(geo_names)} 个区县，adcode={adcode}）")

                    if city:
                        report_name_diff(geo_names, await load_district_names(session, city.id))
    finally:
        await engine.dispose()

    if failed:
        print(f"\n失败城市: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
